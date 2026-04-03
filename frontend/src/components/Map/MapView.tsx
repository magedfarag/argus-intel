import { useEffect, useRef, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// P3-3.1: deck.gl TripsLayer overlay for maritime/aviation tracks
import { MapboxOverlay } from "@deck.gl/mapbox";
import { TripsLayer } from "@deck.gl/geo-layers";
import type { Aoi, ImageryItem, CanonicalEvent } from "../../api/types";
import type { Map as MaplibreMap } from "maplibre-gl";
import type { Trip } from "../../hooks/useTracks";

/** Minimum zoom level below which TripsLayer trails are hidden (P3-3.7). */
const TRACKS_MIN_ZOOM = 7;

interface Props {
  aois: Aoi[];
  imageryItems: ImageryItem[];
  events: CanonicalEvent[];
  onAoiDraw?: (geometry: GeoJSON.Geometry) => void;
  drawMode: "none" | "polygon" | "bbox";
  selectedAoiId: string | null;
  onAoiClick?: (id: string) => void;
  onEventClick?: (event: CanonicalEvent) => void;
  showImageryLayer: boolean;
  showEventLayer: boolean;
  // P2-1.5: GDELT contextual event layer
  gdeltEvents?: CanonicalEvent[];
  showGdeltLayer?: boolean;
  // P3-3.2/3.3: deck.gl TripsLayer for maritime / aviation tracks
  trips?: Trip[];
  currentTime?: number;     // Unix seconds; defaults to end of time window
  showShipsLayer?: boolean;
  showAircraftLayer?: boolean;
  trailLength?: number;     // seconds of visible trail (default 300)
}

export function MapView({
  aois, imageryItems, events, onAoiDraw, drawMode,
  selectedAoiId, onAoiClick, onEventClick,
  showImageryLayer, showEventLayer,
  gdeltEvents = [], showGdeltLayer = false,
  trips = [], currentTime, showShipsLayer = false, showAircraftLayer = false,
  trailLength = 300,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MaplibreMap | null>(null);
  const drawCoordsRef = useRef<[number, number][]>([]);
  const deckOverlayRef = useRef<MapboxOverlay | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: [45.0, 25.0], // Middle East
      zoom: 4,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");

    // P3-3.1: attach deck.gl overlay for TripsLayer
    const overlay = new MapboxOverlay({ layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    deckOverlayRef.current = overlay;

    // P3-3.7: hide TripsLayer at low zoom (graceful degradation)
    map.on("zoom", () => {
      if (overlay && map.getZoom() < TRACKS_MIN_ZOOM) {
        overlay.setProps({ layers: [] });
      }
    });

    return () => {
      try { map.removeControl(overlay as unknown as maplibregl.IControl); } catch (_) { /* ignore */ }
      deckOverlayRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update AOI layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("aois") as maplibregl.GeoJSONSource | undefined;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: aois.map(a => ({
        type: "Feature",
        id: a.id,
        geometry: a.geometry as GeoJSON.Geometry,
        properties: { id: a.id, name: a.name, selected: a.id === selectedAoiId },
      })),
    };
    if (src) {
      src.setData(fc);
    } else {
      map.addSource("aois", { type: "geojson", data: fc });
      map.addLayer({
        id: "aois-fill",
        type: "fill",
        source: "aois",
        paint: { "fill-color": ["case", ["get", "selected"], "#1e6fce", "#2196f3"], "fill-opacity": 0.15 },
      });
      map.addLayer({
        id: "aois-line",
        type: "line",
        source: "aois",
        paint: { "line-color": "#1e6fce", "line-width": 2 },
      });
      map.on("click", "aois-fill", (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (id) onAoiClick?.(id);
      });
    }
  }, [aois, selectedAoiId, onAoiClick]);

  // Update imagery footprints layer (P1-3.9)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("imagery") as maplibregl.GeoJSONSource | undefined;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showImageryLayer ? imageryItems.map(item => ({
        type: "Feature",
        geometry: item.geometry as GeoJSON.Geometry,
        properties: { id: item.item_id, collection: item.collection, cloud_cover: item.cloud_cover },
      })) : [],
    };
    if (src) { src.setData(fc); } else {
      map.addSource("imagery", { type: "geojson", data: fc });
      map.addLayer({
        id: "imagery-fill",
        type: "fill",
        source: "imagery",
        paint: { "fill-color": "#4caf50", "fill-opacity": 0.1 },
      });
      map.addLayer({
        id: "imagery-line",
        type: "line",
        source: "imagery",
        paint: { "line-color": "#4caf50", "line-width": 1, "line-dasharray": [2, 2] },
      });
    }
  }, [imageryItems, showImageryLayer]);

  // Update event markers layer (P1-4.6)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("events") as maplibregl.GeoJSONSource | undefined;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showEventLayer ? events
        .filter(e => e.geometry?.type === "Point")
        .map(evt => ({
          type: "Feature",
          geometry: evt.geometry as GeoJSON.Geometry,
          properties: { id: evt.event_id, source: evt.source, type: evt.event_type },
        })) : [],
    };
    if (src) { src.setData(fc); } else {
      map.addSource("events", { type: "geojson", data: fc, cluster: true, clusterMaxZoom: 12 });
      map.addLayer({
        id: "events-circle",
        type: "circle",
        source: "events",
        filter: ["!", ["has", "point_count"]],
        paint: { "circle-radius": 6, "circle-color": "#f59e0b", "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
      });
      map.on("click", "events-circle", (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (id) {
          const evt = events.find(ev => ev.event_id === id);
          if (evt) onEventClick?.(evt);
        }
      });
    }
  }, [events, showEventLayer, onEventClick]);

  // P2-1.5: GDELT contextual event cluster layer (purple theme)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("gdelt") as maplibregl.GeoJSONSource | undefined;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showGdeltLayer
        ? gdeltEvents
            .filter(e => e.geometry?.type === "Point")
            .map(evt => ({
              type: "Feature",
              geometry: evt.geometry as GeoJSON.Geometry,
              properties: { id: evt.event_id, source: evt.source, confidence: evt.confidence ?? 0.5 },
            }))
        : [],
    };
    if (src) {
      src.setData(fc);
    } else {
      map.addSource("gdelt", { type: "geojson", data: fc, cluster: true, clusterMaxZoom: 12, clusterRadius: 40 });
      map.addLayer({
        id: "gdelt-clusters",
        type: "circle",
        source: "gdelt",
        filter: ["has", "point_count"],
        paint: {
          "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 50, 28],
          "circle-color": ["step", ["get", "point_count"], "#9c27b0", 10, "#7b1fa2", 50, "#4a148c"],
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 1,
        },
      });
      map.addLayer({
        id: "gdelt-cluster-count",
        type: "symbol",
        source: "gdelt",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 11 },
        paint: { "text-color": "#fff" },
      });
      map.addLayer({
        id: "gdelt-point",
        type: "circle",
        source: "gdelt",
        filter: ["!", ["has", "point_count"]],
        paint: { "circle-radius": 5, "circle-color": "#9c27b0", "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
      });
    }
  }, [gdeltEvents, showGdeltLayer]);

  // P3-3.2/3.3: deck.gl TripsLayer — maritime (cyan) and aviation (orange) tracks
  useEffect(() => {
    const overlay = deckOverlayRef.current;
    const map = mapRef.current;
    if (!overlay || !map) return;
    if (map.getZoom() < TRACKS_MIN_ZOOM || (!showShipsLayer && !showAircraftLayer)) {
      overlay.setProps({ layers: [] });
      return;
    }
    const t = currentTime ?? Date.now() / 1000;
    const tl = trailLength;
    const shipTrips = trips.filter(tr => tr.entityType === "ship");
    const aircraftTrips = trips.filter(tr => tr.entityType === "aircraft");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layers: any[] = [];
    if (showShipsLayer && shipTrips.length > 0) {
      layers.push(new TripsLayer({
        id: "ships-trips",
        data: shipTrips,
        getPath: (d: Trip) => d.waypoints as unknown as [number, number][],
        getTimestamps: (d: Trip) => d.waypoints.map(w => w[2]),
        getColor: [0, 188, 212] as [number, number, number],
        opacity: 0.8,
        widthMinPixels: 2,
        rounded: true,
        trailLength: tl,
        currentTime: t,
      }));
    }
    if (showAircraftLayer && aircraftTrips.length > 0) {
      layers.push(new TripsLayer({
        id: "aircraft-trips",
        data: aircraftTrips,
        getPath: (d: Trip) => d.waypoints as unknown as [number, number][],
        getTimestamps: (d: Trip) => d.waypoints.map(w => w[2]),
        getColor: [255, 87, 34] as [number, number, number],
        opacity: 0.8,
        widthMinPixels: 2,
        rounded: true,
        trailLength: tl,
        currentTime: t,
      }));
    }
    overlay.setProps({ layers });
  }, [trips, currentTime, trailLength, showShipsLayer, showAircraftLayer]);

  // Draw interaction handler
  const handleMapClick = useCallback((e: maplibregl.MapMouseEvent) => {
    if (drawMode === "none") return;
    drawCoordsRef.current.push([e.lngLat.lng, e.lngLat.lat]);
    if (drawMode === "bbox" && drawCoordsRef.current.length === 2) {
      const [[x1, y1], [x2, y2]] = drawCoordsRef.current;
      const polygon: GeoJSON.Geometry = {
        type: "Polygon",
        coordinates: [[[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]],
      };
      onAoiDraw?.(polygon);
      drawCoordsRef.current = [];
    } else if (drawMode === "polygon" && drawCoordsRef.current.length >= 3) {
      // Double-click closes polygon
    }
  }, [drawMode, onAoiDraw]);

  const handleDblClick = useCallback(() => {
    if (drawMode === "polygon" && drawCoordsRef.current.length >= 3) {
      const coords = [...drawCoordsRef.current, drawCoordsRef.current[0]];
      const polygon: GeoJSON.Geometry = { type: "Polygon", coordinates: [coords] };
      onAoiDraw?.(polygon);
      drawCoordsRef.current = [];
    }
  }, [drawMode, onAoiDraw]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.on("click", handleMapClick);
    map.on("dblclick", handleDblClick);
    map.getCanvas().style.cursor = drawMode !== "none" ? "crosshair" : "";
    return () => { map.off("click", handleMapClick); map.off("dblclick", handleDblClick); };
  }, [drawMode, handleMapClick, handleDblClick]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }} data-testid="map-container" />
  );
}