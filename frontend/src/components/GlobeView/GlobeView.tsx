// P2-5: Globe-projection view using MapLibre GL.
// Replaces globe.gl (static JPEG texture → blurry on zoom) with MapLibre's
// native globe projection which streams vector tiles at full resolution at
// every zoom level — identical to the 2D view but rendered as a 3D sphere.
import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { TripsLayer } from "@deck.gl/geo-layers";
import type { Aoi, CanonicalEvent } from "../../api/types";
import type { Trip } from "../../hooks/useTracks";

interface Props {
  aois: Aoi[];
  events: CanonicalEvent[];
  gdeltEvents?: CanonicalEvent[];
  trips?: Trip[];
  showEventLayer?: boolean;
  showGdeltLayer?: boolean;
  showShipsLayer?: boolean;
  showAircraftLayer?: boolean;
}

function toFeatureCollection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

export function GlobeView({
  aois, events, gdeltEvents = [], trips = [],
  showEventLayer = true, showGdeltLayer = false,
  showShipsLayer = true, showAircraftLayer = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<MapboxOverlay | null>(null);
  const [styleLoaded, setStyleLoaded] = useState(false);

  // Initialise MapLibre with globe projection
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [56.1, 26.2], // Strait of Hormuz
      zoom: 3,
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");

    const overlay = new MapboxOverlay({ layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    deckRef.current = overlay;

    map.on("load", () => {
      // setProjection requires the style to be loaded — must be inside "load"
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (map as any).setProjection({ type: "globe" });
      setStyleLoaded(true);
    });

    return () => {
      setStyleLoaded(false);
      deckRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // AOI fill + border
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    if (map.getLayer("g-aoi-fill")) map.removeLayer("g-aoi-fill");
    if (map.getLayer("g-aoi-line")) map.removeLayer("g-aoi-line");
    if (map.getSource("g-aois")) map.removeSource("g-aois");

    map.addSource("g-aois", {
      type: "geojson",
      data: toFeatureCollection(
        aois
          .filter(a => a.geometry.type === "Polygon" || a.geometry.type === "MultiPolygon")
          .map(a => ({ type: "Feature" as const, geometry: a.geometry, properties: { name: a.name } }))
      ),
    });
    map.addLayer({ id: "g-aoi-fill", type: "fill", source: "g-aois", paint: { "fill-color": "#3b82f6", "fill-opacity": 0.18 } });
    map.addLayer({ id: "g-aoi-line", type: "line", source: "g-aois", paint: { "line-color": "#60a5fa", "line-width": 2 } });
  }, [aois, styleLoaded]);

  // AOI name labels
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    if (map.getLayer("g-aoi-labels")) map.removeLayer("g-aoi-labels");
    if (map.getSource("g-aoi-label-pts")) map.removeSource("g-aoi-label-pts");

    const pts = aois
      .filter(a => a.geometry.type === "Polygon")
      .map(a => {
        const ring = (a.geometry.coordinates as number[][][])[0];
        const lng = ring.reduce((s, c) => s + c[0], 0) / ring.length;
        const lat = ring.reduce((s, c) => s + c[1], 0) / ring.length;
        return { type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [lng, lat] }, properties: { name: a.name } };
      });

    map.addSource("g-aoi-label-pts", { type: "geojson", data: toFeatureCollection(pts) });
    map.addLayer({
      id: "g-aoi-labels", type: "symbol", source: "g-aoi-label-pts",
      layout: { "text-field": ["get", "name"], "text-size": 13, "text-anchor": "bottom", "text-offset": [0, -0.5] },
      paint: { "text-color": "#f1f5f9", "text-halo-color": "#1e3a5f", "text-halo-width": 2 },
    });
  }, [aois, styleLoaded]);

  // Event circles (amber)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    if (map.getLayer("g-events")) map.removeLayer("g-events");
    if (map.getSource("g-events")) map.removeSource("g-events");

    const features = showEventLayer
      ? events
          .filter(e => e.geometry?.type === "Point")
          .map(e => ({
            type: "Feature" as const,
            geometry: e.geometry as GeoJSON.Point,
            properties: { label: e.event_type.replace(/_/g, " ") + " · " + new Date(e.event_time).toLocaleDateString() },
          }))
      : [];

    map.addSource("g-events", { type: "geojson", data: toFeatureCollection(features) });
    map.addLayer({
      id: "g-events", type: "circle", source: "g-events",
      paint: { "circle-radius": 5, "circle-color": "#f59e0b", "circle-stroke-width": 1.5, "circle-stroke-color": "#fff" },
    });
  }, [events, showEventLayer, styleLoaded]);

  // GDELT circles (purple)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    if (map.getLayer("g-gdelt")) map.removeLayer("g-gdelt");
    if (map.getSource("g-gdelt")) map.removeSource("g-gdelt");

    const features = showGdeltLayer
      ? gdeltEvents
          .filter(e => e.geometry?.type === "Point")
          .map(e => ({
            type: "Feature" as const,
            geometry: e.geometry as GeoJSON.Point,
            properties: {},
          }))
      : [];

    map.addSource("g-gdelt", { type: "geojson", data: toFeatureCollection(features) });
    map.addLayer({
      id: "g-gdelt", type: "circle", source: "g-gdelt",
      paint: { "circle-radius": 4, "circle-color": "#c084fc", "circle-stroke-width": 1, "circle-stroke-color": "#fff" },
    });
  }, [gdeltEvents, showGdeltLayer, styleLoaded]);

  // Ship / aircraft tracks via deck.gl TripsLayer
  useEffect(() => {
    const overlay = deckRef.current;
    if (!overlay) return;

    const filtered = trips.filter(t => t.type === "ship" ? showShipsLayer : showAircraftLayer);
    const trailLength = 86400 * 35; // show full 35-day window
    const currentTime = Date.now() / 1000;

    overlay.setProps({
      layers: [
        new TripsLayer({
          id: "g-trips",
          data: filtered,
          getPath: d => d.waypoints.map(w => [w[0], w[1]] as [number, number]),
          getTimestamps: d => d.waypoints.map(w => w[2]),
          getColor: d => d.type === "ship" ? [34, 211, 238, 220] : [251, 146, 60, 220],
          currentTime,
          trailLength,
          widthMinPixels: 2,
        }),
      ],
    });
  }, [trips, showShipsLayer, showAircraftLayer]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%" }}
      data-testid="globe-container"
    />
  );
}

