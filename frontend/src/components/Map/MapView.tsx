import { useEffect, useRef, useCallback, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// P3-3.1: deck.gl TripsLayer overlay for maritime/aviation tracks
import { MapboxOverlay } from "@deck.gl/mapbox";
import { TripsLayer } from "@deck.gl/geo-layers";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { Aoi, ImageryItem, CanonicalEvent } from "../../api/types";
import type { Map as MaplibreMap } from "maplibre-gl";
import type { Trip } from "../../hooks/useTracks";
import type { SatellitePass, AirspaceRestriction, GpsJammingEvent, StrikeEvent } from "../../types/operationalLayers";
import type { DetectionOverlay } from "../../types/sensorFusion";
import { MapLegend } from "./MapLegend";
import type { RenderMode } from "../../types/renderModes";
import { RENDER_MODE_CONFIGS } from "../../types/renderModes";

/** Minimum zoom level below which TripsLayer trails are hidden (P3-3.7). */
const TRACKS_MIN_ZOOM = 7;

// -- Helper: current position, heading, speed for each active entity
function computeEntityPositions(trips: Trip[], t: number): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const trip of trips) {
    const pts = trip.waypoints.filter(w => w[2] <= t);
    if (!pts.length) continue;
    const last = pts[pts.length - 1];
    if (t - last[2] > 86400) continue; // skip stale (>24h)
    let heading = 0;
    let speedKts = 0;
    if (pts.length >= 2) {
      const prev = pts[pts.length - 2];
      heading = (Math.atan2(last[0] - prev[0], last[1] - prev[1]) * 180 / Math.PI + 360) % 360;
      const dt = last[2] - prev[2];
      if (dt > 0) {
        const dLat = (last[1] - prev[1]) * Math.PI / 180;
        const dLng = (last[0] - prev[0]) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 + Math.cos(prev[1] * Math.PI / 180) * Math.cos(last[1] * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
        const distKm = 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        speedKts = Math.round((distKm / dt) * 3600 / 1.852 * 10) / 10;
      }
    }
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [last[0], last[1]] },
      properties: { id: trip.id, entityType: trip.entityType, heading: Math.round(heading), speedKts, lastSeenUnix: last[2] },
    });
  }
  return { type: "FeatureCollection", features };
}

// -- Helper: draw an upward-pointing arrow on a canvas, return raw ImageData
function makeArrowImageData(r: number, g: number, b: number): ImageData {
  const S = 24;
  const canvas = document.createElement("canvas");
  canvas.width = S; canvas.height = S;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, S, S);
  ctx.fillStyle = `rgb(${r},${g},${b})`;
  ctx.beginPath();
  ctx.moveTo(S / 2, 1);
  ctx.lineTo(S - 3, S - 4);
  ctx.lineTo(S / 2, S - 9);
  ctx.lineTo(3, S - 4);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  return ctx.getImageData(0, 0, S, S);
}

// -- Helper: build HTML string for entity popup
function buildEntityPopupHtml(
  id: string, entityType: string, heading: number,
  speedKts: number, lastSeenUnix: number, lng: number, lat: number,
): string {
  const icon = entityType === "ship" ? "\u{1F6A2}" : "\u2708\uFE0F";
  const typeClass = entityType === "ship" ? "entity-popup-ship" : "entity-popup-aircraft";
  const lastSeen = lastSeenUnix
    ? new Date(lastSeenUnix * 1000).toISOString().slice(0, 16).replace("T", " ") + "Z"
    : "\u2014";
  const speedLabel = entityType === "ship" ? `${speedKts} kts` : `${Math.round(speedKts * 1.852)} km/h`;
  const latStr = `${Math.abs(lat).toFixed(4)}\u00B0${lat >= 0 ? "N" : "S"}`;
  const lngStr = `${Math.abs(lng).toFixed(4)}\u00B0${lng >= 0 ? "E" : "W"}`;
  return `<div class="entity-popup ${typeClass}">
    <div class="entity-popup-header">${icon} ${entityType.toUpperCase()}</div>
    <div class="entity-popup-id">${id}</div>
    <div class="entity-popup-grid">
      <span class="ep-label">Heading</span><span class="ep-val">${heading}\u00B0</span>
      <span class="ep-label">Speed</span><span class="ep-val">${speedLabel}</span>
      <span class="ep-label">Position</span><span class="ep-val">${latStr} ${lngStr}</span>
      <span class="ep-label">Last seen</span><span class="ep-val">${lastSeen}</span>
    </div>
  </div>`;
}

function resolveMapStyle(id: string) {
  const raster = (url: string, attribution: string) => ({
    version: 8 as const,
    sources: { base: { type: "raster" as const, tiles: [url], tileSize: 256, attribution } },
    layers: [{ id: "base", type: "raster" as const, source: "base" }],
  });
  switch (id) {
    case "dark":      return raster("https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", "© CARTO, © OpenStreetMap contributors");
    case "light":     return raster("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", "© CARTO, © OpenStreetMap contributors");
    case "satellite": return raster("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", "© Esri");
    default:          return "https://demotiles.maplibre.org/style.json";
  }
}

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
  showGdeltLayer?: boolean;  // P2-3.3: imagery footprint opacity slider
  imageryOpacity?: number;  // 0–1, default 0.1  // P3-3.2/3.3: deck.gl TripsLayer for maritime / aviation tracks
  trips?: Trip[];
  currentTime?: number;     // Unix seconds; defaults to end of time window
  showShipsLayer?: boolean;
  showAircraftLayer?: boolean;
  trailLength?: number;     // seconds of visible trail (default 300)
  baseStyle?: string;
  // Phase 2 operational layers
  showOrbitsLayer?: boolean;
  orbitPasses?: SatellitePass[];
  showAirspaceLayer?: boolean;
  airspaceRestrictions?: AirspaceRestriction[];
  showJammingLayer?: boolean;
  jammingEvents?: GpsJammingEvent[];
  showStrikesLayer?: boolean;
  strikeEvents?: StrikeEvent[];
  // Phase 4 Track D — AI detection overlay
  showDetectionsLayer?: boolean;
  detections?: DetectionOverlay[];
  // Phase 4 Track A — render mode
  renderMode?: RenderMode;
  // Phase 4 Track C — entity selection callback
  onStrikeClick?: (strikeId: string) => void;
  // Phase 4 Track C — camera focus fly-to
  centerPoint?: { lon: number; lat: number };
}

export function MapView({
  aois, imageryItems, events, onAoiDraw, drawMode,
  selectedAoiId, onAoiClick, onEventClick,
  showImageryLayer, showEventLayer,
  gdeltEvents = [], showGdeltLayer = false,
  imageryOpacity = 0.1,
  trips = [], currentTime, showShipsLayer = false, showAircraftLayer = false,
  trailLength = 300, baseStyle = "vector",
  showOrbitsLayer = false, orbitPasses = [],
  showAirspaceLayer = false, airspaceRestrictions = [],
  showJammingLayer = false, jammingEvents = [],
  showStrikesLayer = false, strikeEvents = [],
  showDetectionsLayer = false, detections = [],
  renderMode = "day",
  onStrikeClick,
  centerPoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MaplibreMap | null>(null);
  const drawCoordsRef = useRef<[number, number][]>([]);
  const deckOverlayRef = useRef<MapboxOverlay | null>(null);
  const deckLayersRef = useRef<unknown[]>([]);
  // Stable ref for strike click callback — avoids stale closure in map.on handler
  const onStrikeClickRef = useRef(onStrikeClick);
  useEffect(() => { onStrikeClickRef.current = onStrikeClick; });
  // Track when the MapLibre style finishes loading so data-dependent effects
  // can safely add sources/layers without bailing out on isStyleLoaded().
  const [styleLoaded, setStyleLoaded] = useState(false);
  const initialBaseStyleRef = useRef(baseStyle);
  const isMountedRef = useRef(false);
  const [coordDisplay, setCoordDisplay] = useState("");

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      style: resolveMapStyle(initialBaseStyleRef.current) as any,
      center: [56.1, 26.2], // Strait of Hormuz
      zoom: 8,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");

    // P3-3.1: attach deck.gl overlay for TripsLayer
    const overlay = new MapboxOverlay({ layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    deckOverlayRef.current = overlay;

    // Signal that all base layers are ready, so data-dependent effects can add sources
    map.on("load", () => setStyleLoaded(true));

    // P3-3.7: hide trip layers at low zoom; preserve orbit/jamming layers
    map.on("zoom", () => {
      if (overlay && map.getZoom() < TRACKS_MIN_ZOOM) {
        const nonTripLayers = deckLayersRef.current.filter(
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (l: any) => !String(l.id ?? "").startsWith("ships-") && !String(l.id ?? "").startsWith("aircraft-"),
        );
        overlay.setProps({ layers: nonTripLayers });
      }
    });

    return () => {
      setStyleLoaded(false);
      try { map.removeControl(overlay as unknown as maplibregl.IControl); } catch { /* ignore */ }
      deckOverlayRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Coordinate display on hover
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const onMove = (e: maplibregl.MapMouseEvent) => {
      const { lat, lng } = e.lngLat;
      setCoordDisplay(
        `${Math.abs(lat).toFixed(4)}\u00B0${lat >= 0 ? "N" : "S"}\u2002\u00B7\u2002${Math.abs(lng).toFixed(4)}\u00B0${lng >= 0 ? "E" : "W"}`
      );
    };
    const onLeave = () => setCoordDisplay("");
    map.on("mousemove", onMove);
    map.getCanvas().addEventListener("mouseleave", onLeave);
    return () => {
      map.off("mousemove", onMove);
      map.getCanvas().removeEventListener("mouseleave", onLeave);
    };
  }, []);

  // Update AOI layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
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
  }, [aois, selectedAoiId, onAoiClick, styleLoaded]);

  // Update imagery footprints layer (P1-3.9, P2-3.3 opacity)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const src = map.getSource("imagery") as maplibregl.GeoJSONSource | undefined;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showImageryLayer ? imageryItems.map(item => ({
        type: "Feature",
        geometry: item.geometry as GeoJSON.Geometry,
        properties: { id: item.item_id, collection: item.collection, cloud_cover: item.cloud_cover },
      })) : [],
    };
    if (src) {
      src.setData(fc);
      // P2-3.3: live opacity update without recreating layers
      if (map.getLayer("imagery-fill")) {
        map.setPaintProperty("imagery-fill", "fill-opacity", showImageryLayer ? imageryOpacity : 0);
      }
    } else {
      map.addSource("imagery", { type: "geojson", data: fc });
      map.addLayer({
        id: "imagery-fill",
        type: "fill",
        source: "imagery",
        paint: { "fill-color": "#4caf50", "fill-opacity": showImageryLayer ? imageryOpacity : 0 },
      });
      map.addLayer({
        id: "imagery-line",
        type: "line",
        source: "imagery",
        paint: { "line-color": "#4caf50", "line-width": 1, "line-dasharray": [2, 2] },
      });
    }
  }, [imageryItems, showImageryLayer, imageryOpacity, styleLoaded]);

  // Update event markers layer (P1-4.6)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
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
  }, [events, showEventLayer, onEventClick, styleLoaded]);

  // P2-1.5: GDELT contextual event cluster layer (purple theme)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
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
  }, [gdeltEvents, showGdeltLayer, styleLoaded]);

  // P3-3.2/3.3 + Phase 2: all deck.gl layers (trips, orbits, jamming)
  useEffect(() => {
    const overlay = deckOverlayRef.current;
    const map = mapRef.current;
    if (!overlay || !map) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layers: any[] = [];

    // ── TripsLayer (ships + aircraft, zoom-gated) ──
    if (map.getZoom() >= TRACKS_MIN_ZOOM) {
      const t = currentTime ?? Date.now() / 1000;
      const tl = trailLength;
      const shipTrips = trips.filter(tr => tr.entityType === "ship");
      const aircraftTrips = trips.filter(tr => tr.entityType === "aircraft");
      if (showShipsLayer && shipTrips.length > 0) {
        // Outer glow halo — wide + transparent, creates 3-D neon depth effect
        layers.push(new TripsLayer({
          id: "ships-glow",
          data: shipTrips,
          getPath: (d: Trip) => d.waypoints.map(w => [w[0], w[1]]) as [number, number][],
          getTimestamps: (d: Trip) => d.waypoints.map(w => w[2]),
          getColor: [0, 229, 255] as [number, number, number],
          opacity: 0.18,
          widthMinPixels: 14, capRounded: true, jointRounded: true,
          trailLength: tl, currentTime: t,
        }));
        // Bright core trail
        layers.push(new TripsLayer({
          id: "ships-trips",
          data: shipTrips,
          getPath: (d: Trip) => d.waypoints.map(w => [w[0], w[1]]) as [number, number][],
          getTimestamps: (d: Trip) => d.waypoints.map(w => w[2]),
          getColor: [0, 229, 255] as [number, number, number],
          opacity: 0.9,
          widthMinPixels: 3, capRounded: true, jointRounded: true,
          trailLength: tl, currentTime: t,
        }));
      }
      if (showAircraftLayer && aircraftTrips.length > 0) {
        // Outer glow halo
        layers.push(new TripsLayer({
          id: "aircraft-glow",
          data: aircraftTrips,
          getPath: (d: Trip) => d.waypoints.map(w => [w[0], w[1]]) as [number, number][],
          getTimestamps: (d: Trip) => d.waypoints.map(w => w[2]),
          getColor: [255, 100, 50] as [number, number, number],
          opacity: 0.18,
          widthMinPixels: 14, capRounded: true, jointRounded: true,
          trailLength: tl, currentTime: t,
        }));
        // Bright core trail
        layers.push(new TripsLayer({
          id: "aircraft-trips",
          data: aircraftTrips,
          getPath: (d: Trip) => d.waypoints.map(w => [w[0], w[1]]) as [number, number][],
          getTimestamps: (d: Trip) => d.waypoints.map(w => w[2]),
          getColor: [255, 100, 50] as [number, number, number],
          opacity: 0.9,
          widthMinPixels: 3, capRounded: true, jointRounded: true,
          trailLength: tl, currentTime: t,
        }));
      }
    }

    // ── Orbit ground-track paths (PathLayer) ──
    if (showOrbitsLayer && orbitPasses.length > 0) {
      layers.push(new PathLayer<SatellitePass>({
        id: "orbit-passes",
        data: orbitPasses,
        getPath: (d: SatellitePass) => {
          if (d.footprint_geojson) {
            const poly = d.footprint_geojson as { type: string; coordinates: [number, number][][] };
            if (poly.type === "Polygon" && poly.coordinates?.[0]) {
              return poly.coordinates[0];
            }
          }
          return [[0, 0], [180, 0]] as [number, number][];
        },
        getColor: [0, 255, 136] as [number, number, number],
        getWidth: 2,
        widthUnits: "pixels",
        capRounded: true,
      }));
    }

    // ── GPS Jamming (ScatterplotLayer + HeatmapLayer) ──
    if (showJammingLayer && jammingEvents.length > 0) {
      layers.push(new ScatterplotLayer<GpsJammingEvent>({
        id: "jamming-scatter",
        data: jammingEvents,
        getPosition: (e: GpsJammingEvent) => [e.location_lon, e.location_lat] as [number, number],
        getRadius: (e: GpsJammingEvent) => (e.radius_km ?? 50) * 1000,
        getFillColor: (e: GpsJammingEvent): [number, number, number, number] => [255, 50, 50, Math.round(e.confidence * 180)],
        stroked: true,
        getLineColor: [255, 100, 100, 200] as [number, number, number, number],
        lineWidthMinPixels: 1,
        radiusUnits: "meters",
      }));
      layers.push(new HeatmapLayer<GpsJammingEvent>({
        id: "jamming-heat",
        data: jammingEvents,
        getPosition: (e: GpsJammingEvent) => [e.location_lon, e.location_lat] as [number, number],
        getWeight: (e: GpsJammingEvent) => e.confidence,
        radiusPixels: 60,
        intensity: 1,
        threshold: 0.05,
      }));
    }

    deckLayersRef.current = layers;
    overlay.setProps({ layers });
  }, [trips, currentTime, trailLength, showShipsLayer, showAircraftLayer,
      showOrbitsLayer, orbitPasses, showJammingLayer, jammingEvents, styleLoaded]);

  // Phase 2: Airspace restrictions — fill + dashed line
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const colorExpr = [
      "match", ["get", "restriction_type"],
      "TFR",  "#ff4444",
      "MOA",  "#ffaa00",
      "NFZ",  "#ff0000",
      "ADIZ", "#ff8800",
      "#ffcc00",
    ];
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showAirspaceLayer ? airspaceRestrictions.map(r => ({
        type: "Feature" as const,
        geometry: r.geometry_geojson as GeoJSON.Geometry,
        properties: {
          restriction_id: r.restriction_id,
          name: r.name,
          restriction_type: r.restriction_type,
          valid_from: r.valid_from,
          valid_to: r.valid_to ?? null,
          lower_limit_ft: r.lower_limit_ft ?? null,
          upper_limit_ft: r.upper_limit_ft ?? null,
          is_active: r.is_active,
        },
      })) : [],
    };
    const src = map.getSource("airspace") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(fc);
    } else {
      map.addSource("airspace", { type: "geojson", data: fc });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const ce = colorExpr as any;
      map.addLayer({ id: "airspace-fill", type: "fill", source: "airspace",
        paint: { "fill-color": ce, "fill-opacity": 0.15 } });
      map.addLayer({ id: "airspace-line", type: "line", source: "airspace",
        paint: { "line-color": ce, "line-width": 2, "line-dasharray": [4, 2] } });
      map.on("click", "airspace-fill", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        const alt = p.lower_limit_ft != null
          ? `${p.lower_limit_ft as string}\u2013${(p.upper_limit_ft as string | null) ?? "UNL"} ft`
          : "\u2014";
        const validity = `${(p.valid_from as string | null) ?? "\u2014"} \u2192 ${(p.valid_to as string | null) ?? "open"}`;
        new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(`<div class="entity-popup">
            <div class="entity-popup-header">\u2708 ${p.restriction_type as string}</div>
            <div class="entity-popup-id">${p.name as string}</div>
            <div class="entity-popup-grid">
              <span class="ep-label">Valid</span><span class="ep-val">${validity}</span>
              <span class="ep-label">Altitude</span><span class="ep-val">${alt}</span>
            </div>
          </div>`)
          .addTo(map);
      });
    }
  }, [showAirspaceLayer, airspaceRestrictions, styleLoaded]);

  // Phase 2: Strike events — circle markers by type
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const colorExpr = [
      "match", ["get", "strike_type"],
      "airstrike", "#ff2200",
      "artillery", "#ff8800",
      "missile",   "#ff0044",
      "drone",     "#ff6600",
      "#ff9900",
    ];
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showStrikesLayer ? strikeEvents.map(s => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [s.location_lon, s.location_lat] },
        properties: {
          strike_id: s.strike_id,
          strike_type: s.strike_type,
          confidence: s.confidence,
          occurred_at: s.occurred_at,
          target_description: s.target_description ?? null,
        },
      })) : [],
    };
    const src = map.getSource("strikes") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(fc);
    } else {
      map.addSource("strikes", { type: "geojson", data: fc });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const ce = colorExpr as any;
      map.addLayer({
        id: "strikes-circle", type: "circle", source: "strikes",
        paint: {
          "circle-color": ce,
          "circle-radius": ["*", ["get", "confidence"], 10] as unknown as number,
          "circle-opacity": 0.8,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      map.on("click", "strikes-circle", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        const conf = `${Math.round((p.confidence as number) * 100)}%`;
        new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(`<div class="entity-popup">
            <div class="entity-popup-header">\uD83D\uDCA5 STRIKE</div>
            <div class="entity-popup-id">${(p.strike_type as string).toUpperCase()}</div>
            <div class="entity-popup-grid">
              <span class="ep-label">At</span><span class="ep-val">${p.occurred_at as string}</span>
              <span class="ep-label">Target</span><span class="ep-val">${(p.target_description as string | null) ?? "\u2014"}</span>
              <span class="ep-label">Confidence</span><span class="ep-val">${conf}</span>
            </div>
          </div>`)
          .addTo(map);
        onStrikeClickRef.current?.(p.strike_id as string);
      });
    }
  }, [showStrikesLayer, strikeEvents, styleLoaded]);

  // Phase 4 Track C — fly to camera focus point
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !centerPoint) return;
    map.flyTo({ center: [centerPoint.lon, centerPoint.lat], zoom: 12 });
  }, [centerPoint]);

  // Phase 4 Track D: Detection overlay — AI-detected ground objects
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const detectionColorExpr = [
      "match", ["get", "detection_type"],
      "vehicle",        "#ffdd00",
      "person",         "#ff6600",
      "aircraft",       "#00ccff",
      "vessel",         "#00e5ff",
      "infrastructure", "#aa88ff",
      "#aaaaaa",
    ];
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: showDetectionsLayer
        ? detections
            .filter(d => d.geo_location != null)
            .map(d => ({
              type: "Feature" as const,
              geometry: { type: "Point" as const, coordinates: [d.geo_location!.lon, d.geo_location!.lat] },
              properties: {
                detection_id: d.detection_id,
                observation_id: d.observation_id,
                detection_type: d.detection_type,
                detected_at: d.detected_at,
                confidence: d.confidence,
              },
            }))
        : [],
    };
    const src = map.getSource("detections") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(fc);
    } else {
      map.addSource("detections", { type: "geojson", data: fc });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const ce = detectionColorExpr as any;
      map.addLayer({
        id: "detections-circle", type: "circle", source: "detections",
        paint: {
          "circle-color": ce,
          "circle-radius": ["*", ["get", "confidence"], 10] as unknown as number,
          "circle-opacity": 0.85,
          "circle-stroke-color": "#222222",
          "circle-stroke-width": 1,
        },
      });
      map.on("click", "detections-circle", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        const conf = `${Math.round((p.confidence as number) * 100)}%`;
        const detectedAt = new Date(p.detected_at as string).toLocaleString();
        new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(`<div class="entity-popup">
            <div class="entity-popup-header">🔍 DETECTION</div>
            <div class="entity-popup-id">${(p.detection_type as string).toUpperCase()}</div>
            <div class="entity-popup-grid">
              <span class="ep-label">Detected</span><span class="ep-val">${detectedAt}</span>
              <span class="ep-label">Observation</span><span class="ep-val">${p.observation_id as string}</span>
              <span class="ep-label">Confidence</span><span class="ep-val">${conf}</span>
            </div>
          </div>`)
          .addTo(map);
      });
    }
  }, [showDetectionsLayer, detections, styleLoaded]);

  // Entity position arrows — directional icon for each entity's current head position
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const t = currentTime ?? Date.now() / 1000;
    const active = (trips ?? []).filter(tr =>
      tr.entityType === "ship" ? (showShipsLayer ?? true) : (showAircraftLayer ?? true)
    );
    const data = computeEntityPositions(active, t);

    // Register arrow images (idempotent — no-op if already added)
    if (!map.hasImage("ship-arrow"))     map.addImage("ship-arrow",     makeArrowImageData(0, 229, 255));
    if (!map.hasImage("aircraft-arrow")) map.addImage("aircraft-arrow", makeArrowImageData(255, 87, 34));

    const src = map.getSource("entity-positions") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(data);
      const shipsVis    = (showShipsLayer    ?? true) ? "visible" : "none";
      const aircraftVis = (showAircraftLayer ?? true) ? "visible" : "none";
      const haloVis     = ((showShipsLayer ?? true) || (showAircraftLayer ?? true)) ? "visible" : "none";
      if (map.getLayer("entity-halo"))     map.setLayoutProperty("entity-halo",     "visibility", haloVis);
      if (map.getLayer("entity-ships"))    map.setLayoutProperty("entity-ships",    "visibility", shipsVis);
      if (map.getLayer("entity-aircraft")) map.setLayoutProperty("entity-aircraft", "visibility", aircraftVis);
    } else {
      map.addSource("entity-positions", { type: "geojson", data });
      // Pulse-halo ring rendered behind the directional arrow
      map.addLayer({
        id: "entity-halo", type: "circle", source: "entity-positions",
        paint: {
          "circle-radius": 16,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": ["case", ["==", ["get", "entityType"], "ship"], "#00e5ff", "#ff5722"],
          "circle-opacity": 0,
          "circle-stroke-opacity": 0.45,
        },
      });
      map.addLayer({
        id: "entity-ships", type: "symbol", source: "entity-positions",
        filter: ["==", ["get", "entityType"], "ship"],
        layout: {
          "icon-image": "ship-arrow",
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": 1.1,
          "visibility": (showShipsLayer ?? true) ? "visible" : "none",
        },
      });
      map.addLayer({
        id: "entity-aircraft", type: "symbol", source: "entity-positions",
        filter: ["==", ["get", "entityType"], "aircraft"],
        layout: {
          "icon-image": "aircraft-arrow",
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": 1.1,
          "visibility": (showAircraftLayer ?? true) ? "visible" : "none",
        },
      });
    }
  }, [trips, currentTime, showShipsLayer, showAircraftLayer, styleLoaded]);

  // Entity interactions — click popup + hover cursors (re-attaches on style reload)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const handleEntityClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feat = e.features?.[0];
      if (!feat || feat.geometry.type !== "Point") return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates;
      const p = feat.properties as Record<string, unknown>;
      new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
        .setLngLat([lng, lat])
        .setHTML(buildEntityPopupHtml(
          String(p.id ?? ""), String(p.entityType ?? ""),
          Number(p.heading ?? 0), Number(p.speedKts ?? 0),
          Number(p.lastSeenUnix ?? 0), lng, lat,
        ))
        .addTo(map);
    };
    const cursorOn  = () => { map.getCanvas().style.cursor = "pointer"; };
    const cursorOff = () => { if (drawMode === "none") map.getCanvas().style.cursor = ""; };
    map.on("click",      "entity-ships",    handleEntityClick);
    map.on("click",      "entity-aircraft", handleEntityClick);
    map.on("mouseenter", "entity-ships",    cursorOn);
    map.on("mouseleave", "entity-ships",    cursorOff);
    map.on("mouseenter", "entity-aircraft", cursorOn);
    map.on("mouseleave", "entity-aircraft", cursorOff);
    map.on("mouseenter", "events-circle",   cursorOn);
    map.on("mouseleave", "events-circle",   cursorOff);
    map.on("mouseenter", "aois-fill",       cursorOn);
    map.on("mouseleave", "aois-fill",       cursorOff);
    return () => {
      map.off("click",      "entity-ships",    handleEntityClick);
      map.off("click",      "entity-aircraft", handleEntityClick);
      map.off("mouseenter", "entity-ships",    cursorOn);
      map.off("mouseleave", "entity-ships",    cursorOff);
      map.off("mouseenter", "entity-aircraft", cursorOn);
      map.off("mouseleave", "entity-aircraft", cursorOff);
      map.off("mouseenter", "events-circle",   cursorOn);
      map.off("mouseleave", "events-circle",   cursorOff);
      map.off("mouseenter", "aois-fill",       cursorOn);
      map.off("mouseleave", "aois-fill",       cursorOff);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleLoaded]);

  // Change basemap style when baseStyle prop changes (skip initial mount)
  useEffect(() => {
    if (!isMountedRef.current) { isMountedRef.current = true; return; }
    const map = mapRef.current;
    if (!map) return;
    setStyleLoaded(false);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.setStyle(resolveMapStyle(baseStyle) as any);
    map.once("style.load", () => setStyleLoaded(true));
  }, [baseStyle]);
  // ── Draw interaction handler with live preview ───────────────────────────
  const [drawCoords, setDrawCoords] = useState<[number, number][]>([]);
  const mouseCoordRef = useRef<[number, number] | null>(null);

  // Reset draw state when mode changes
  useEffect(() => {
    setDrawCoords([]);
    drawCoordsRef.current = [];
    mouseCoordRef.current = null;
  }, [drawMode]);

  const handleMapClick = useCallback((e: maplibregl.MapMouseEvent) => {
    if (drawMode === "none") return;
    const pt: [number, number] = [e.lngLat.lng, e.lngLat.lat];
    drawCoordsRef.current.push(pt);
    setDrawCoords([...drawCoordsRef.current]);
    if (drawMode === "bbox" && drawCoordsRef.current.length === 2) {
      const [[x1, y1], [x2, y2]] = drawCoordsRef.current;
      const polygon: GeoJSON.Geometry = {
        type: "Polygon",
        coordinates: [[[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]],
      };
      onAoiDraw?.(polygon);
      drawCoordsRef.current = [];
      setDrawCoords([]);
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
      setDrawCoords([]);
    }
  }, [drawMode, onAoiDraw]);

  // Live preview: update draw-preview GeoJSON source on mouse move
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handleMouseMove = (e: maplibregl.MapMouseEvent) => {
      if (drawMode === "none") return;
      mouseCoordRef.current = [e.lngLat.lng, e.lngLat.lat];
      updateDrawPreview(map, drawCoordsRef.current, mouseCoordRef.current, drawMode);
    };
    map.on("mousemove", handleMouseMove);
    return () => { map.off("mousemove", handleMouseMove); };
  }, [drawMode]);

  // Update preview when drawCoords change
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    if (drawMode === "none" || drawCoords.length === 0) {
      clearDrawPreview(map);
      return;
    }
    updateDrawPreview(map, drawCoords, mouseCoordRef.current, drawMode);
  }, [drawCoords, drawMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.on("click", handleMapClick);
    map.on("dblclick", handleDblClick);
    map.getCanvas().style.cursor = drawMode !== "none" ? "crosshair" : "";
    return () => { map.off("click", handleMapClick); map.off("dblclick", handleDblClick); };
  }, [drawMode, handleMapClick, handleDblClick]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }} data-testid="map-container">
      <div
        ref={containerRef}
        style={{ width: "100%", height: "100%", filter: RENDER_MODE_CONFIGS[renderMode].cssFilter }}
      />
      {renderMode !== "day" && RENDER_MODE_CONFIGS[renderMode].tintColor != null && (
        <div
          style={{
            position: "absolute", inset: 0,
            background: RENDER_MODE_CONFIGS[renderMode].tintColor,
            opacity: RENDER_MODE_CONFIGS[renderMode].tintOpacity ?? 0,
            pointerEvents: "none",
            zIndex: 1,
          }}
        />
      )}
      {renderMode !== "day" && (
        <div
          style={{
            position: "absolute", top: 8, right: 60,
            background: "rgba(0,0,0,0.55)",
            color: "#f8fafc",
            fontFamily: "monospace", fontSize: 10, fontWeight: 700,
            padding: "2px 7px", borderRadius: 4,
            pointerEvents: "none", zIndex: 10,
            letterSpacing: "0.08em",
          }}
        >
          {RENDER_MODE_CONFIGS[renderMode].label.toUpperCase()}
        </div>
      )}
      <MapLegend
        showShips={showShipsLayer}
        showAircraft={showAircraftLayer}
        showEvents={showEventLayer}
        showGdelt={showGdeltLayer}
        showImagery={showImageryLayer}
        showOrbits={showOrbitsLayer}
        showAirspace={showAirspaceLayer}
        showJamming={showJammingLayer}
        showStrikes={showStrikesLayer}
        showDetections={showDetectionsLayer}
      />
      {coordDisplay && <div className="map-coord-display">{coordDisplay}</div>}
    </div>
  );
}

// ── Draw preview helpers ──────────────────────────────────────────────────
const DRAW_SOURCE = "draw-preview";
const DRAW_FILL_LAYER = "draw-preview-fill";
const DRAW_LINE_LAYER = "draw-preview-line";
const DRAW_VERTEX_LAYER = "draw-preview-vertices";

function ensureDrawLayers(map: MaplibreMap) {
  if (!map.getSource(DRAW_SOURCE)) {
    map.addSource(DRAW_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: DRAW_FILL_LAYER,
      type: "fill",
      source: DRAW_SOURCE,
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": "#1e6fce", "fill-opacity": 0.15 },
    });
    map.addLayer({
      id: DRAW_LINE_LAYER,
      type: "line",
      source: DRAW_SOURCE,
      paint: { "line-color": "#1e6fce", "line-width": 2, "line-dasharray": [3, 2] },
    });
    map.addLayer({
      id: DRAW_VERTEX_LAYER,
      type: "circle",
      source: DRAW_SOURCE,
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-radius": 5,
        "circle-color": "#1e6fce",
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 2,
      },
    });
  }
}

function updateDrawPreview(
  map: MaplibreMap,
  coords: [number, number][],
  mouse: [number, number] | null,
  mode: "polygon" | "bbox",
) {
  if (!map.isStyleLoaded()) return;
  ensureDrawLayers(map);
  const src = map.getSource(DRAW_SOURCE) as maplibregl.GeoJSONSource;
  if (!src) return;

  const features: GeoJSON.Feature[] = [];

  // Vertex markers
  for (const c of coords) {
    features.push({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: {} });
  }

  if (mode === "bbox" && coords.length === 1 && mouse) {
    const [x1, y1] = coords[0];
    const [x2, y2] = mouse;
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [[[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]] },
      properties: {},
    });
  } else if (mode === "polygon" && coords.length >= 2) {
    const ring = mouse ? [...coords, mouse, coords[0]] : [...coords, coords[0]];
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [ring] },
      properties: {},
    });
  } else if (mode === "polygon" && coords.length === 1 && mouse) {
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: [coords[0], mouse] },
      properties: {},
    });
  }

  src.setData({ type: "FeatureCollection", features });
}

function clearDrawPreview(map: MaplibreMap) {
  if (!map.isStyleLoaded()) return;
  const src = map.getSource(DRAW_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (src) src.setData({ type: "FeatureCollection", features: [] });
}