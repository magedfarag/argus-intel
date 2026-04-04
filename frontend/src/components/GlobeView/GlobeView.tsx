// P2-5: Globe-projection view using MapLibre GL.
// Replaces globe.gl (static JPEG texture → blurry on zoom) with MapLibre's
// native globe projection which streams vector tiles at full resolution at
// every zoom level — identical to the 2D view but rendered as a 3D sphere.
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { TripsLayer, Tile3DLayer } from "@deck.gl/geo-layers";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { useScenePerformance } from "../../hooks/useScenePerformance";
import type { Aoi, CanonicalEvent } from "../../api/types";
import type { Trip } from "../../hooks/useTracks";
import type { SatellitePass, AirspaceRestriction, GpsJammingEvent, StrikeEvent } from "../../types/operationalLayers";
import type { DetectionOverlay } from "../../types/sensorFusion";
import { chokepointsApi } from "../../api/client";
import { darkShipsApi } from "../../api/client";
import { MapLegend } from "../Map/MapLegend";
import type { RenderMode } from "../../types/renderModes";
import { RENDER_MODE_CONFIGS } from "../../types/renderModes";

/** Globe always uses vector tiles — raster styles break the globe projection */
const GLOBE_STYLE_URL = "https://demotiles.maplibre.org/style.json";

// -- Helper: current position, heading, speed for each entity
function computeEntityPositions(trips: Trip[], t: number): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const trip of trips) {
    const pts = trip.waypoints.filter(w => w[2] <= t);
    if (!pts.length) continue;
    const last = pts[pts.length - 1];
    if (t - last[2] > 86400) continue;
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

// -- Build HTML string for entity click popup
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

interface Props {
  aois: Aoi[];
  events: CanonicalEvent[];
  gdeltEvents?: CanonicalEvent[];
  trips?: Trip[];
  showEventLayer?: boolean;
  showGdeltLayer?: boolean;
  showShipsLayer?: boolean;
  showAircraftLayer?: boolean;
  currentTime?: number;   // Unix seconds — drives TripsLayer animation position
  trailLength?: number;   // seconds of visible trail
  // Phase 2 operational layers
  showOrbitsLayer?: boolean;
  orbitPasses?: SatellitePass[];
  showAirspaceLayer?: boolean;
  airspaceRestrictions?: AirspaceRestriction[];
  showJammingLayer?: boolean;
  jammingEvents?: GpsJammingEvent[];
  showStrikesLayer?: boolean;
  strikeEvents?: StrikeEvent[];
  // Phase 3 Track B — terrain + buildings
  showTerrainLayer?: boolean;
  show3dBuildingsLayer?: boolean;
  // Phase 3 Track D — perf overlay
  showPerfOverlay?: boolean;
  // Phase 4 Track A — render mode
  renderMode?: RenderMode;
  // Phase 4 Track D — AI detection overlays
  showDetectionsLayer?: boolean;
  detections?: DetectionOverlay[];
  // Phase 4 Track C — entity selection + camera focus
  selectedEntityId?: string | null;
  centerPoint?: { lon: number; lat: number };
}

function toFeatureCollection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

function getDetectionColor(type: string): [number, number, number, number] {
  switch (type) {
    case 'vehicle':        return [255, 221,   0, 220];
    case 'person':         return [255, 102,   0, 220];
    case 'aircraft':       return [  0, 204, 255, 220];
    case 'vessel':         return [  0, 229, 255, 220];
    case 'infrastructure': return [170, 136, 255, 220];
    default:               return [170, 170, 170, 220];
  }
}


export function GlobeView({
  aois, events, gdeltEvents = [], trips = [],
  showEventLayer = true, showGdeltLayer = false,
  showShipsLayer = true, showAircraftLayer = true,
  currentTime,
  trailLength = 86400 * 35,
  showOrbitsLayer = false, orbitPasses = [],
  showAirspaceLayer = false, airspaceRestrictions = [],
  showJammingLayer = false, jammingEvents = [],
  showStrikesLayer = false, strikeEvents = [],
  showTerrainLayer = false,
  show3dBuildingsLayer = false,
  showPerfOverlay = false,
  renderMode = "day",
  showDetectionsLayer = false, detections = [],
  selectedEntityId = null,
  centerPoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<MapboxOverlay | null>(null);
  const [styleLoaded, setStyleLoaded] = useState(false);
  const godsEyeFiredRef = useRef(false);   // P6-7: one-shot entry animation
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tripsLayersRef = useRef<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const orbitLayersRef = useRef<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const jammingLayersRef = useRef<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const buildingsLayerRef = useRef<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const detectionsLayerRef = useRef<any[]>([]);
  // Capture showTerrainLayer at mount time — MapLibre terrain requires style reload to toggle
  const showTerrainAtMountRef = useRef(showTerrainLayer);

  // P6: fetch chokepoints + dark ships for overlay layers
  const { data: cpData } = useQuery({ queryKey: ["chokepoints"], queryFn: () => chokepointsApi.list(), staleTime: 60_000 });
  const { data: darkShipData } = useQuery({ queryKey: ["dark-ships"], queryFn: () => darkShipsApi.list(), staleTime: 120_000 });

  // Initialise MapLibre with globe projection — always vector (raster styles break globe)
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: GLOBE_STYLE_URL,
      center: [30, 20],   // Africa / Middle East centre for good global perspective
      zoom: 1.5,
      pitch: 30,          // tilt for 3-D sphere feel
      bearing: 20,
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");

    const overlay = new MapboxOverlay({ layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    deckRef.current = overlay;

    map.on("load", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (map as any).setProjection({ type: "globe" });

      // Track B — DEM terrain elevation (opt-in via showTerrainLayer at mount)
      if (showTerrainAtMountRef.current) {
        const demUrl = (import.meta.env.VITE_DEM_TILES_URL as string | undefined)
          ?? "https://demotiles.maplibre.org/terrain-tiles/tiles.json";
        map.addSource("dem", { type: "raster-dem", url: demUrl, tileSize: 256 });
        map.setTerrain({ source: "dem", exaggeration: 1.2 });
        map.addLayer({
          id: "terrain-hillshade",
          type: "hillshade",
          source: "dem",
          paint: { "hillshade-shadow-color": "#122A2A", "hillshade-intensity": 0.5 },
        });
      }

      setStyleLoaded(true);

      // P6-7: God's Eye entry animation — descend from orbit to Hormuz
      if (!godsEyeFiredRef.current) {
        godsEyeFiredRef.current = true;
        setTimeout(() => {
          map.flyTo({
            center: [56.52, 26.35],   // Strait of Hormuz centroid
            zoom: 5.5,
            pitch: 48,
            bearing: -20,
            speed: 0.28,
            curve: 1.8,
            easing: (t: number) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
          });
        }, 800);  // brief pause after style loads
      }
    });

    return () => {
      setStyleLoaded(false);
      deckRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Auto-rotate globe slowly until user interacts
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    let active = true;
    let rafId: number;
    function spin() {
      if (!active || !mapRef.current) return;
      mapRef.current.setBearing((mapRef.current.getBearing() - 0.04 + 360) % 360);
      rafId = requestAnimationFrame(spin);
    }
    rafId = requestAnimationFrame(spin);
    const stop = () => { active = false; cancelAnimationFrame(rafId); };
    map.on("mousedown", stop);
    map.on("touchstart", stop);
    return () => { active = false; cancelAnimationFrame(rafId); map.off("mousedown", stop); map.off("touchstart", stop); };
  }, [styleLoaded]);

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

  // Ship / aircraft tracks via deck.gl TripsLayer — glow halo + bright core (3D neon effect)
  useEffect(() => {
    const overlay = deckRef.current;
    if (!overlay) return;
    const t = currentTime ?? Date.now() / 1000;
    const shipTrips    = trips.filter(tr => tr.entityType === "ship"     && showShipsLayer);
    const aircraftTrips = trips.filter(tr => tr.entityType === "aircraft" && showAircraftLayer);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layers: any[] = [];
    if (shipTrips.length) {
      layers.push(new TripsLayer({
        id: "g-ships-glow", data: shipTrips,
        getPath: d => d.waypoints.map(w => [w[0], w[1]] as [number, number]),
        getTimestamps: d => d.waypoints.map(w => w[2]),
        getColor: [0, 229, 255] as [number, number, number], opacity: 0.18,
        widthMinPixels: 14, capRounded: true, jointRounded: true,
        trailLength, currentTime: t,
      }));
      layers.push(new TripsLayer({
        id: "g-ships-trips", data: shipTrips,
        getPath: d => d.waypoints.map(w => [w[0], w[1]] as [number, number]),
        getTimestamps: d => d.waypoints.map(w => w[2]),
        getColor: [0, 229, 255] as [number, number, number], opacity: 0.9,
        widthMinPixels: 3, capRounded: true, jointRounded: true,
        trailLength, currentTime: t,
      }));
    }
    if (aircraftTrips.length) {
      layers.push(new TripsLayer({
        id: "g-aircraft-glow", data: aircraftTrips,
        getPath: d => d.waypoints.map(w => [w[0], w[1]] as [number, number]),
        getTimestamps: d => d.waypoints.map(w => w[2]),
        getColor: [255, 100, 50] as [number, number, number], opacity: 0.18,
        widthMinPixels: 14, capRounded: true, jointRounded: true,
        trailLength, currentTime: t,
      }));
      layers.push(new TripsLayer({
        id: "g-aircraft-trips", data: aircraftTrips,
        getPath: d => d.waypoints.map(w => [w[0], w[1]] as [number, number]),
        getTimestamps: d => d.waypoints.map(w => w[2]),
        getColor: [255, 100, 50] as [number, number, number], opacity: 0.9,
        widthMinPixels: 3, capRounded: true, jointRounded: true,
        trailLength, currentTime: t,
      }));
    }
    tripsLayersRef.current = layers;
    overlay.setProps({ layers: [...tripsLayersRef.current, ...orbitLayersRef.current, ...jammingLayersRef.current, ...buildingsLayerRef.current, ...detectionsLayerRef.current] });
  }, [trips, showShipsLayer, showAircraftLayer, currentTime, trailLength]);

  // Entity position arrows on the globe (directional icons at track head)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const t = currentTime ?? Date.now() / 1000;
    const active = trips.filter(tr =>
      tr.entityType === "ship" ? (showShipsLayer ?? true) : (showAircraftLayer ?? true)
    );
    const data = computeEntityPositions(active, t);

    if (!map.hasImage("ship-arrow"))     map.addImage("ship-arrow",     makeArrowImageData(0, 229, 255));
    if (!map.hasImage("aircraft-arrow")) map.addImage("aircraft-arrow", makeArrowImageData(255, 87, 34));

    const src = map.getSource("g-entity-positions") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(data);
      const shipsVis    = (showShipsLayer    ?? true) ? "visible" : "none";
      const aircraftVis = (showAircraftLayer ?? true) ? "visible" : "none";
      const haloVis     = ((showShipsLayer ?? true) || (showAircraftLayer ?? true)) ? "visible" : "none";
      if (map.getLayer("g-entity-halo"))     map.setLayoutProperty("g-entity-halo",     "visibility", haloVis);
      if (map.getLayer("g-entity-ships"))    map.setLayoutProperty("g-entity-ships",    "visibility", shipsVis);
      if (map.getLayer("g-entity-aircraft")) map.setLayoutProperty("g-entity-aircraft", "visibility", aircraftVis);
    } else {
      map.addSource("g-entity-positions", { type: "geojson", data });
      // Pulse halo ring behind the directional arrow
      map.addLayer({
        id: "g-entity-halo", type: "circle", source: "g-entity-positions",
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
        id: "g-entity-ships", type: "symbol", source: "g-entity-positions",
        filter: ["==", ["get", "entityType"], "ship"],
        layout: {
          "icon-image": "ship-arrow",
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": 1.1,
        },
      });
      map.addLayer({
        id: "g-entity-aircraft", type: "symbol", source: "g-entity-positions",
        filter: ["==", ["get", "entityType"], "aircraft"],
        layout: {
          "icon-image": "aircraft-arrow",
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": 1.1,
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
    const cursorOff = () => { map.getCanvas().style.cursor = ""; };
    map.on("click",      "g-entity-ships",    handleEntityClick);
    map.on("click",      "g-entity-aircraft", handleEntityClick);
    map.on("mouseenter", "g-entity-ships",    cursorOn);
    map.on("mouseleave", "g-entity-ships",    cursorOff);
    map.on("mouseenter", "g-entity-aircraft", cursorOn);
    map.on("mouseleave", "g-entity-aircraft", cursorOff);
    map.on("mouseenter", "g-events",          cursorOn);
    map.on("mouseleave", "g-events",          cursorOff);
    return () => {
      map.off("click",      "g-entity-ships",    handleEntityClick);
      map.off("click",      "g-entity-aircraft", handleEntityClick);
      map.off("mouseenter", "g-entity-ships",    cursorOn);
      map.off("mouseleave", "g-entity-ships",    cursorOff);
      map.off("mouseenter", "g-entity-aircraft", cursorOn);
      map.off("mouseleave", "g-entity-aircraft", cursorOff);
      map.off("mouseenter", "g-events",          cursorOn);
      map.off("mouseleave", "g-events",          cursorOff);
    };
  }, [styleLoaded]);

  // P6-9: Chokepoint polygon overlay — threat-coloured fill + label
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded || !cpData?.chokepoints?.length) return;

    const THREAT_COLORS: Record<number, string> = {
      1: "#22c55e", 2: "#84cc16", 3: "#eab308",
      4: "#f97316", 5: "#ef4444",
    };

    // Remove stale layers/sources
    ["g-choke-fill", "g-choke-line", "g-choke-labels"].forEach(l => { if (map.getLayer(l)) map.removeLayer(l); });
    ["g-chokepoints", "g-choke-label-pts"].forEach(s => { if (map.getSource(s)) map.removeSource(s); });

    // Build polygon features using the GeoJSON geometry directly from the API
    const features = cpData.chokepoints.map(cp => ({
      type: "Feature" as const,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      geometry: cp.geometry as any,
      properties: {
        name: cp.name,
        threat: cp.threat_level,
        flow: cp.daily_flow_mbbl,
        color: THREAT_COLORS[cp.threat_level] ?? "#ef4444",
      },
    }));

    const labelPts = cpData.chokepoints.map(cp => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [cp.centroid.lon, cp.centroid.lat] },
      properties: { label: `${cp.name}\n${cp.daily_flow_mbbl}M bbl/d` },
    }));

    map.addSource("g-chokepoints", { type: "geojson", data: toFeatureCollection(features) });
    map.addLayer({
      id: "g-choke-fill", type: "fill", source: "g-chokepoints",
      paint: { "fill-color": ["get", "color"], "fill-opacity": 0.13 },
    });
    map.addLayer({
      id: "g-choke-line", type: "line", source: "g-chokepoints",
      paint: { "line-color": ["get", "color"], "line-width": 2, "line-dasharray": [4, 3] },
    });
    map.addSource("g-choke-label-pts", { type: "geojson", data: toFeatureCollection(labelPts) });
    map.addLayer({
      id: "g-choke-labels", type: "symbol", source: "g-choke-label-pts",
      layout: { "text-field": ["get", "label"], "text-size": 11, "text-anchor": "center", "text-max-width": 10 },
      paint: { "text-color": "#f8fafc", "text-halo-color": "#00000099", "text-halo-width": 1.5 },
    });
  }, [cpData, styleLoaded]);

  // P6-10: Dark-ship pulsing circles — orange halos with MMSI label
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    ["g-dark-ships"].forEach(l => { if (map.getLayer(l)) map.removeLayer(l); });
    ["g-dark-ship-src"].forEach(s => { if (map.getSource(s)) map.removeSource(s); });

    const candidates = darkShipData?.candidates ?? [];
    const features = candidates.map(ds => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [ds.last_known_lon, ds.last_known_lat] },
      properties: { label: ds.vessel_name ?? ds.mmsi, conf: Math.round(ds.confidence * 100) },
    }));

    map.addSource("g-dark-ship-src", { type: "geojson", data: toFeatureCollection(features) });
    map.addLayer({
      id: "g-dark-ships", type: "circle", source: "g-dark-ship-src",
      paint: {
        "circle-radius": 10,
        "circle-color": "#f97316",
        "circle-opacity": 0.35,
        "circle-stroke-width": 2,
        "circle-stroke-color": "#f97316",
      },
    });
  }, [darkShipData, styleLoaded]);

  // Orbit passes — deck.gl PathLayer (footprint polygon ring traced as a path on globe)
  useEffect(() => {
    const passesWithFootprints = showOrbitsLayer
      ? orbitPasses.filter(
          (p): p is SatellitePass & { footprint_geojson: GeoJSON.Polygon } =>
            !!p.footprint_geojson && (p.footprint_geojson as GeoJSON.Polygon).type === "Polygon",
        )
      : [];
    orbitLayersRef.current = passesWithFootprints.length
      ? [new PathLayer<SatellitePass & { footprint_geojson: GeoJSON.Polygon }>({
          id: "globe-orbit-passes",
          data: passesWithFootprints,
          getPath: p => (p.footprint_geojson as GeoJSON.Polygon).coordinates[0] as [number, number][],
          getColor: [0, 255, 136, 200] as [number, number, number, number],
          getWidth: 2,
          widthMinPixels: 1,
        })]
      : [];
    deckRef.current?.setProps({ layers: [...tripsLayersRef.current, ...orbitLayersRef.current, ...jammingLayersRef.current, ...buildingsLayerRef.current, ...detectionsLayerRef.current] });
  }, [showOrbitsLayer, orbitPasses]);

  // Airspace restrictions — MapLibre fill + dashed line layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    ["globe-airspace-fill", "globe-airspace-line"].forEach(l => { if (map.getLayer(l)) map.removeLayer(l); });
    if (map.getSource("globe-airspace")) map.removeSource("globe-airspace");

    const features = showAirspaceLayer
      ? airspaceRestrictions
          .filter(r => r.is_active)
          .map(r => ({
            type: "Feature" as const,
            geometry: r.geometry_geojson as GeoJSON.Geometry,
            properties: { restriction_type: r.restriction_type, name: r.name, is_active: r.is_active },
          }))
      : [];

    map.addSource("globe-airspace", { type: "geojson", data: toFeatureCollection(features) });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const restrictionColorExpr: any = ["match", ["get", "restriction_type"],
      "TFR", "#ff4444", "NFZ", "#ff0000", "MOA", "#ffaa00", "ADIZ", "#ff8800", "#ffcc00",
    ];
    map.addLayer({
      id: "globe-airspace-fill", type: "fill", source: "globe-airspace",
      paint: { "fill-color": restrictionColorExpr, "fill-opacity": 0.2 },
    });
    map.addLayer({
      id: "globe-airspace-line", type: "line", source: "globe-airspace",
      paint: { "line-color": restrictionColorExpr, "line-width": 1.5, "line-dasharray": [3, 2] },
    });
  }, [showAirspaceLayer, airspaceRestrictions, styleLoaded]);

  // Jamming events — deck.gl ScatterplotLayer (radius in meters)
  useEffect(() => {
    jammingLayersRef.current = showJammingLayer && jammingEvents.length
      ? [new ScatterplotLayer<GpsJammingEvent>({
          id: "globe-jamming",
          data: jammingEvents,
          getPosition: e => [e.location_lon, e.location_lat] as [number, number],
          getRadius: e => (e.radius_km ?? 50) * 1000,
          getFillColor: e => [255, 50, 50, Math.round(e.confidence * 160)] as [number, number, number, number],
          radiusUnits: "meters",
          stroked: true,
          getLineColor: [255, 100, 100, 220] as [number, number, number, number],
          lineWidthMinPixels: 1,
        })]
      : [];
    deckRef.current?.setProps({ layers: [...tripsLayersRef.current, ...orbitLayersRef.current, ...jammingLayersRef.current, ...buildingsLayerRef.current, ...detectionsLayerRef.current] });
  }, [showJammingLayer, jammingEvents]);

  // Track B — 3D Buildings via deck.gl Tile3DLayer
  useEffect(() => {
    const tile3dUrl = (import.meta.env.VITE_3D_TILES_URL as string | undefined)
      ?? "https://tile.googleapis.com/v1/3dtiles/root.json";
    buildingsLayerRef.current = show3dBuildingsLayer
      ? [new Tile3DLayer({
          id: "buildings-3d-tiles",
          data: tile3dUrl,
          opacity: 0.8,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          onTilesetLoad: (_tileset: any) => {
            // deck.gl Tile3DLayer handles camera automatically
          },
        })]
      : [];
    deckRef.current?.setProps({ layers: [...tripsLayersRef.current, ...orbitLayersRef.current, ...jammingLayersRef.current, ...buildingsLayerRef.current, ...detectionsLayerRef.current] });
  }, [show3dBuildingsLayer]);

  // Strike events — MapLibre circle layer (type-coloured, zoom-scaled radius)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    ["globe-strikes-circle"].forEach(l => { if (map.getLayer(l)) map.removeLayer(l); });
    if (map.getSource("globe-strikes")) map.removeSource("globe-strikes");

    const features = showStrikesLayer
      ? strikeEvents.map(s => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [s.location_lon, s.location_lat] },
          properties: { strike_id: s.strike_id, strike_type: s.strike_type, confidence: s.confidence, occurred_at: s.occurred_at, selected: s.strike_id === selectedEntityId ? 1 : 0 },
        }))
      : [];

    map.addSource("globe-strikes", { type: "geojson", data: toFeatureCollection(features) });
    map.addLayer({
      id: "globe-strikes-circle", type: "circle", source: "globe-strikes",
      paint: {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "circle-color": ["match", ["get", "strike_type"],
          "airstrike", "#ff2200", "artillery", "#ff8800", "missile", "#ff0044", "drone", "#ff6600", "#ff9900",
        ] as any,
        // Double radius for selected strike; otherwise zoom-interpolated normal size.
        // ["zoom"] must be the top-level interpolate input — cannot nest inside ["*"].
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "circle-radius": ["interpolate", ["linear"], ["zoom"],
          1, ["case", ["==", ["get", "selected"], 1], 6, 3],
          6, ["case", ["==", ["get", "selected"], 1], ["*", ["get", "confidence"], 24], ["*", ["get", "confidence"], 12]],
        ] as any,
        "circle-opacity": 0.85,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1,
      },
    });
  }, [showStrikesLayer, strikeEvents, selectedEntityId, styleLoaded]);

  // Phase 4 Track D — AI detection overlay (deck.gl ScatterplotLayer)
  useEffect(() => {
    detectionsLayerRef.current = showDetectionsLayer && detections.length
      ? [new ScatterplotLayer<DetectionOverlay>({
          id: "globe-detections",
          data: detections.filter(d => d.geo_location != null),
          getPosition: d => [d.geo_location!.lon, d.geo_location!.lat] as [number, number],
          getRadius: d => d.confidence * 5000,
          getFillColor: d => getDetectionColor(d.detection_type),
          opacity: 0.8,
          stroked: true,
          getLineColor: [255, 255, 255, 180] as [number, number, number, number],
          lineWidthMinPixels: 1,
          radiusUnits: "meters",
        })]
      : [];
    deckRef.current?.setProps({ layers: [...tripsLayersRef.current, ...orbitLayersRef.current, ...jammingLayersRef.current, ...buildingsLayerRef.current, ...detectionsLayerRef.current] });
  }, [showDetectionsLayer, detections]);

  // Phase 4 Track C — fly to camera focus point
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !centerPoint) return;
    map.flyTo({ center: [centerPoint.lon, centerPoint.lat], zoom: 8, pitch: 30 });
  }, [centerPoint]);

  // Track D — FPS / entity count perf report
  const entityCount = trips.length;
  const perfReport = useScenePerformance(entityCount);
  const renderModeConfig = RENDER_MODE_CONFIGS[renderMode];

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }} data-testid="globe-container">
      <div
        ref={containerRef}
        style={{ width: "100%", height: "100%", filter: renderModeConfig.cssFilter }}
      />
      {renderMode !== "day" && renderModeConfig.tintColor != null && (
        <div
          style={{
            position: "absolute", inset: 0,
            background: renderModeConfig.tintColor,
            opacity: renderModeConfig.tintOpacity ?? 0,
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
          {renderModeConfig.label.toUpperCase()}
        </div>
      )}
      <MapLegend
        showShips={showShipsLayer}
        showAircraft={showAircraftLayer}
        showEvents={showEventLayer}
        showGdelt={showGdeltLayer}
      />
      {showPerfOverlay && (
        <div style={{
          position: "absolute", top: 8, left: 8,
          background: "rgba(0,0,0,0.6)", color: "#0ff",
          fontFamily: "monospace", fontSize: "11px",
          padding: "4px 8px", borderRadius: 4, pointerEvents: "none", zIndex: 10,
        }}>
          {perfReport.fps} FPS · {perfReport.frameMs}ms{perfReport.isDenseView ? " · DENSE" : ""}
        </div>
      )}
    </div>
  );
}

