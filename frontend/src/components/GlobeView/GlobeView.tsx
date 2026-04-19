// P2-5: Globe-projection view using MapLibre GL.
// Replaces globe.gl (static JPEG texture → blurry on zoom) with MapLibre's
// native globe projection which streams vector tiles at full resolution at
// every zoom level — identical to the 2D view but rendered as a 3D sphere.
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { TripsLayer, Tile3DLayer } from "@deck.gl/geo-layers";
import { PathLayer, ScatterplotLayer, IconLayer } from "@deck.gl/layers";
import { useScenePerformance } from "../../hooks/useScenePerformance";
import type { Aoi, CanonicalEvent } from "../../api/types";
import type { Trip, TrackWaypoint } from "../../hooks/useTracks";
import type { SatellitePass, AirspaceRestriction, GpsJammingEvent, StrikeEvent } from "../../types/operationalLayers";
import type { DetectionOverlay } from "../../types/sensorFusion";
import { chokepointsApi } from "../../api/client";
import { darkShipsApi } from "../../api/client";
import { MapLegend } from "../Map/MapLegend";
import type { RenderMode } from "../../types/renderModes";
import { RENDER_MODE_CONFIGS } from "../../types/renderModes";
import { normalizeEntityAltitudeM } from "../../utils/entityAltitude";

/** Globe always uses vector tiles — raster styles break the globe projection.
 * OpenFreeMap: free, no API key, no registration (https://openfreemap.org/). */
const GLOBE_STYLE_URL = "https://tiles.openfreemap.org/styles/bright";
const TRACK_LAYER_REFRESH_MS = 120;

interface TrackHead {
  id: string;
  entityType: Trip["entityType"];
  lng: number;
  lat: number;
  altitudeM: number;
  heading: number;
  speedKts: number;
  lastSeenUnix: number;
}

// -- Helper: binary search for the last waypoint index with timestamp <= t.
// Waypoints are pre-sorted by timestamp (useTracks sorts them).
// Replaces O(n) .filter() with O(log n) per trip — critical during animation.
function lastWaypointIndex(waypoints: TrackWaypoint[], t: number): number {
  let lo = 0, hi = waypoints.length - 1, best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (waypoints[mid][2] <= t) { best = mid; lo = mid + 1; }
    else { hi = mid - 1; }
  }
  return best;
}

// -- Helper: current position, heading, speed for each entity
function getTrackHeads(trips: Trip[], t: number): TrackHead[] {
  const heads: TrackHead[] = [];
  for (const trip of trips) {
    const idx = lastWaypointIndex(trip.waypoints, t);
    if (idx < 0) continue;
    const last = trip.waypoints[idx];
    if (t - last[2] > 86400) continue;
    let heading = 0;
    let speedKts = 0;
    if (idx >= 1) {
      const prev = trip.waypoints[idx - 1];
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
    const altitudeM = normalizeEntityAltitudeM(trip.entityType, last[3]);
    heads.push({
      id: trip.id,
      entityType: trip.entityType,
      lng: last[0],
      lat: last[1],
      altitudeM,
      heading: Math.round(heading),
      speedKts,
      lastSeenUnix: last[2],
    });
  }
  return heads;
}

function computeEntityPositions(trips: Trip[], t: number): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const head of getTrackHeads(trips, t)) {
    // Aircraft icons rendered at altitude, ships at sea level
    const coordinates = head.entityType === "aircraft" 
      ? [head.lng, head.lat, head.altitudeM]
      : [head.lng, head.lat];
    
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates },
      properties: {
        id: head.id,
        entityType: head.entityType,
        heading: head.heading,
        speedKts: head.speedKts,
        lastSeenUnix: head.lastSeenUnix,
        altitudeM: head.altitudeM,
      },
    });
  }
  return { type: "FeatureCollection", features };
}

function resolveTripDisplayAltitudeM(
  trip: Trip,
  activeHeadAltitudesM: ReadonlyMap<string, number>,
): number {
  const headAltitudeM = activeHeadAltitudesM.get(trip.id);
  if (headAltitudeM != null) return headAltitudeM;

  const lastWaypoint = trip.waypoints[trip.waypoints.length - 1];
  return normalizeEntityAltitudeM(trip.entityType, lastWaypoint?.[3]);
}

function getAircraftDisplayPath(
  trip: Trip,
  activeHeadAltitudesM: ReadonlyMap<string, number>,
): [number, number, number][] {
  const altitudeM = resolveTripDisplayAltitudeM(trip, activeHeadAltitudesM);
  return trip.waypoints.map((waypoint): [number, number, number] => [
    waypoint[0],
    waypoint[1],
    altitudeM,
  ]);
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
  speedKts: number, lastSeenUnix: number, lng: number, lat: number, altitudeM = 0,
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
      ${entityType === "aircraft" ? `<span class="ep-label">Altitude</span><span class="ep-val">${Math.round(altitudeM)} m</span>` : ""}
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
  isAnimating?: boolean;  // true = continuous playback, false = viewing specific point in time
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
  // Intel signals
  signalEvents?: CanonicalEvent[];
  showSignalsLayer?: boolean;
  // Phase 4 Track C — entity selection + camera focus
  selectedEntityId?: string | null;
  centerPoint?: { lon: number; lat: number };
  // Selected AOI ID for globe context
  selectedAoiId?: string | null;
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
  isAnimating = false,
  showOrbitsLayer = false, orbitPasses = [],
  showAirspaceLayer = false, airspaceRestrictions = [],
  showJammingLayer = false, jammingEvents = [],
  showStrikesLayer = false, strikeEvents = [],
  showTerrainLayer = false,
  show3dBuildingsLayer = false,
  showPerfOverlay = false,
  renderMode = "day",
  showDetectionsLayer = false, detections = [],
  signalEvents = [], showSignalsLayer = false,
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const aircraftIconLayerRef = useRef<any[]>([]);
  const lastTrackLayerBuildMsRef = useRef<number>(0);

  /** Single point of truth for deck.gl setProps — merges all Deck.gl layer buckets. */
  function flushOverlay() {
    const overlay = deckRef.current;
    if (!overlay) return;
    overlay.setProps({ layers: [
      ...tripsLayersRef.current,
      ...orbitLayersRef.current,
      ...jammingLayersRef.current,
      ...buildingsLayerRef.current,
      ...detectionsLayerRef.current,
      ...aircraftIconLayerRef.current,
    ]});
  }
  // Capture showTerrainLayer at mount time — MapLibre terrain requires style reload to toggle
  const showTerrainAtMountRef = useRef(showTerrainLayer);

  const shipTrips = useMemo(
    () => (showShipsLayer ? trips.filter(tr => tr.entityType === "ship") : []),
    [trips, showShipsLayer],
  );
  const aircraftTrips = useMemo(
    () => (showAircraftLayer ? trips.filter(tr => tr.entityType === "aircraft") : []),
    [trips, showAircraftLayer],
  );
  const activeTrips = useMemo(
    () => [...shipTrips, ...aircraftTrips],
    [shipTrips, aircraftTrips],
  );


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

    // Ensure the canvas adapts whenever the container is resized (flex/window resize)
    let resizeTimeout: ReturnType<typeof setTimeout>;
    const handleResize = () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        if (mapRef.current) {
          mapRef.current.resize();
        }
      }, 100);
    };
    const ro = new ResizeObserver(handleResize);
    ro.observe(containerRef.current!);
    
    // Backup: Also listen to window resize events
    window.addEventListener('resize', handleResize);

    // Defensive font remapper — patches any loaded style that references fonts not
    // hosted on OpenFreeMap (e.g. old Carto Voyager style migrated its glyphs URL to
    // tiles.openfreemap.org but still specifies "Open Sans Regular" which 404s there).
    const FONT_REMAP: Record<string, string> = {
      "Open Sans Regular":      "Noto Sans Regular",
      "Open Sans Bold":         "Noto Sans Bold",
      "Open Sans Italic":       "Noto Sans Italic",
      "Open Sans SemiBold":     "Noto Sans Bold",
      "Open Sans ExtraBold":    "Noto Sans Bold",
      "Arial Unicode MS Regular": "Noto Sans Regular",
      "Arial Unicode MS Bold":    "Noto Sans Bold",
    };
    const patchStyleFonts = () => {
      const style = map.getStyle();
      if (!style?.layers) return;
      for (const layer of style.layers) {
        if (layer.type !== "symbol") continue;
        const fonts = (layer as maplibregl.SymbolLayerSpecification).layout?.["text-font"];
        if (!Array.isArray(fonts)) continue;
        // fonts may be ExpressionSpecification[] — only remap plain string entries
        const remapped = fonts.map((f) => (typeof f === "string" ? (FONT_REMAP[f] ?? f) : f));
        if (remapped.some((f, i) => f !== fonts[i])) {
          map.setLayoutProperty(layer.id, "text-font", remapped);
        }
      }
    };
    map.on("styledata", patchStyleFonts);

    map.on("load", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (map as any).setProjection({ type: "globe" });

      // Ensure map is properly sized after load
      requestAnimationFrame(() => {
        map.resize();
      });

      // Track B — DEM terrain elevation (opt-in via showTerrainLayer at mount)
      // Terrain now available in all modes (analyst request - removed demo mode restriction)
      const demUrl = import.meta.env.VITE_DEM_TILES_URL as string | undefined;
      // Use Terrarium terrain tiles (free, reliable, hosted on AWS)
      const defaultTerrainSource = {
        type: "raster-dem" as const,
        tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
        minzoom: 0,
        maxzoom: 15,
        tileSize: 256,
        encoding: "terrarium" as const,
      };
      
      if (showTerrainAtMountRef.current) {
        try {
          if (demUrl) {
            // Use custom DEM URL if provided
            map.addSource("dem", { type: "raster-dem", url: demUrl, tileSize: 256 });
          } else {
            // Use Terrarium tiles as default
            map.addSource("dem", defaultTerrainSource);
          }
          map.setTerrain({ source: "dem", exaggeration: 1.5 });
          map.addLayer({
            id: "terrain-hillshade",
            type: "hillshade",
            source: "dem",
            paint: { "hillshade-shadow-color": "#122A2A", "hillshade-exaggeration": 0.5 },
          });
          console.log('[GlobeView] Terrain enabled with 1.5x exaggeration using', demUrl ? 'custom DEM' : 'Terrarium tiles');
        } catch (err) {
          console.warn('[GlobeView] Terrain layer failed, continuing without terrain:', err);
        }
      }

      setStyleLoaded(true);

      // Clean up stale layers/sources from previous code versions (e.g. old unified g-entity-positions)
      const staleLayers = ["g-entity-halo", "g-entity-aircraft", "g-entity-positions"];
      for (const id of staleLayers) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      if (map.getSource("g-entity-positions")) map.removeSource("g-entity-positions");

      // Expose map instance for Playwright demo recording (dev / demo mode only)
      (window as Window & { __argusMap?: maplibregl.Map }).__argusMap = map;

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
      clearTimeout(resizeTimeout);
      window.removeEventListener('resize', handleResize);
      ro.disconnect();
      setStyleLoaded(false);
      deckRef.current = null;
      delete (window as Window & { __argusMap?: maplibregl.Map }).__argusMap;
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
          .map(a => ({ type: "Feature" as const, geometry: a.geometry as unknown as GeoJSON.Geometry, properties: { name: a.name } }))
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
      layout: { "text-field": ["get", "name"], "text-size": 13, "text-anchor": "bottom", "text-offset": [0, -0.5], "text-font": ["Noto Sans Regular"] },
      paint: { "text-color": "#f1f5f9", "text-halo-color": "#1e3a5f", "text-halo-width": 2 },
    });
  }, [aois, styleLoaded]);

  // Event circles (amber) — create once, update data in-place to prevent flashing
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    // Create layer only if it doesn't exist
    if (!map.getSource("g-events")) {
      map.addSource("g-events", { type: "geojson", data: toFeatureCollection([]) });
      map.addLayer({
        id: "g-events", type: "circle", source: "g-events",
        paint: { "circle-radius": 5, "circle-color": "#f59e0b", "circle-stroke-width": 1.5, "circle-stroke-color": "#fff" },
      });
    }

    // Update data in-place without recreating layer
    const features = showEventLayer
      ? events
          .filter(e => e.geometry?.type === "Point")
          .map(e => ({
            type: "Feature" as const,
            geometry: e.geometry as GeoJSON.Point,
            properties: {
              event_id: e.event_id,
              event_type: e.event_type,
              event_time: e.event_time,
              source: e.source,
              confidence: e.confidence ?? 0.5,
              title: (e.attributes as Record<string, unknown> | undefined)?.title ?? null,
              description: (e.attributes as Record<string, unknown> | undefined)?.description ?? null,
              headline: (e.attributes as Record<string, unknown> | undefined)?.headline ?? null,
              url: (e.attributes as Record<string, unknown> | undefined)?.url ?? null,
            },
          }))
      : [];

    const src = map.getSource("g-events") as maplibregl.GeoJSONSource;
    if (src) src.setData(toFeatureCollection(features));
  }, [events, showEventLayer, styleLoaded]);

  // GDELT circles (purple)
  // GDELT layer — create once, update data in-place to prevent flashing
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    // Create layer only if it doesn't exist
    if (!map.getSource("g-gdelt")) {
      map.addSource("g-gdelt", { type: "geojson", data: toFeatureCollection([]) });
      map.addLayer({
        id: "g-gdelt", type: "circle", source: "g-gdelt",
        paint: { "circle-radius": 4, "circle-color": "#c084fc", "circle-stroke-width": 1, "circle-stroke-color": "#fff" },
      });
    }

    // Update data in-place without recreating layer
    const features = showGdeltLayer
      ? gdeltEvents
          .filter(e => e.geometry?.type === "Point")
          .map(e => ({
            type: "Feature" as const,
            geometry: e.geometry as GeoJSON.Point,
            properties: {
              id: e.event_id,
              source: e.source,
              type: e.event_type,
              date: e.event_time,
              confidence: e.confidence ?? 0.5,
              headline: (e.attributes as Record<string, unknown> | undefined)?.headline ?? null,
              url: (e.attributes as Record<string, unknown> | undefined)?.url ?? null,
              source_publication: (e.attributes as Record<string, unknown> | undefined)?.source_publication ?? null,
            },
          }))
      : [];

    const src = map.getSource("g-gdelt") as maplibregl.GeoJSONSource;
    if (src) src.setData(toFeatureCollection(features));
  }, [gdeltEvents, showGdeltLayer, styleLoaded, mapRef]);

  // Intel signal circles — seismic, hazard, weather, conflict, maritime warning, military, thermal, space weather, AQ
  // Intel signals layer — create once, update data in-place to prevent flashing
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;

    // Create layer only if it doesn't exist
    if (!map.getSource("g-signals")) {
      map.addSource("g-signals", { type: "geojson", data: toFeatureCollection([]) });
      map.addLayer({
        id: "g-signals", type: "circle", source: "g-signals",
        paint: {
          "circle-radius": 5,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#fff",
          "circle-color": [
            "case",
            ["==", ["get", "type"], "seismic_event"],            "#ef4444",
            ["==", ["get", "type"], "natural_hazard_event"],     "#f97316",
            ["==", ["get", "type"], "weather_observation"],      "#3b82f6",
            ["==", ["get", "type"], "conflict_event"],           "#dc2626",
            ["==", ["get", "type"], "maritime_warning"],         "#06b6d4",
            ["==", ["get", "type"], "military_site_observation"],"#7c3aed",
            ["==", ["get", "type"], "thermal_anomaly_event"],    "#ea580c",
            ["==", ["get", "type"], "space_weather_event"],      "#8b5cf6",
            ["==", ["get", "type"], "air_quality_observation"],  "#22c55e",
            "#22d3ee",
          ],
        },
      });
    }

    // Update data in-place without recreating layer
    const features = showSignalsLayer
      ? signalEvents
          .filter(e => e.geometry?.type === "Point")
          .map(e => ({
            type: "Feature" as const,
            geometry: e.geometry as GeoJSON.Point,
            properties: {
              type: e.event_type,
              id: e.event_id,
              source: e.source,
              date: e.event_time,
              confidence: e.confidence ?? 0.5,
            },
          }))
      : [];

    const src = map.getSource("g-signals") as maplibregl.GeoJSONSource;
    if (src) src.setData(toFeatureCollection(features));
  }, [signalEvents, showSignalsLayer, styleLoaded]);

  // Ship / aircraft tracks via deck.gl TripsLayer — glow halo + bright core (3D neon effect)
  useEffect(() => {
    const overlay = deckRef.current;
    if (!overlay) return;
    const t = currentTime ?? Date.now() / 1000;

    const nowMs = performance.now();
    const shouldRebuildLayers =
      tripsLayersRef.current.length === 0
      || nowMs - lastTrackLayerBuildMsRef.current >= TRACK_LAYER_REFRESH_MS;

    if (!shouldRebuildLayers) {
      // When animation stops, currentTime stops changing so this effect only fires once more.
      // If we hit the fast path with !isAnimating, trails must be cleared immediately — otherwise
      // they persist forever (no more currentTime changes = no more effect triggers).
      if (!isAnimating) {
        if (tripsLayersRef.current.length > 0) {
          tripsLayersRef.current = [];
          flushOverlay();
        }
        return;
      }
      const updatedLayers = tripsLayersRef.current.map(layer => {
        const id = String((layer as { id?: string }).id ?? "");
        if (id.includes("-trips") || id.includes("-glow")) {
          return layer.clone({ currentTime: t });
        }
        return layer;
      });
      tripsLayersRef.current = updatedLayers;
      flushOverlay();
      return;
    }

    lastTrackLayerBuildMsRef.current = nowMs;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layers: any[] = [];
    const aircraftHeadAltitudesM = new Map(
      getTrackHeads(aircraftTrips, t).map((head) => [head.id, head.altitudeM] as const),
    );
    
    // Trails only shown when animating (moving)
    if (isAnimating) {
      if (shipTrips.length) {
        // Ships rendered at sea level — omit Z to drape paths on the map surface.
        layers.push(new TripsLayer({
          id: "g-ships-trips", data: shipTrips,
          getPath: (d: Trip) => d.waypoints.map((w: TrackWaypoint) => [w[0], w[1]]) as [number, number][],
          getTimestamps: (d: Trip) => d.waypoints.map((w: TrackWaypoint) => w[2]),
          getColor: [20, 186, 140] as [number, number, number], opacity: 0.9,
          widthMinPixels: 3,
          capRounded: true,
          jointRounded: true,
          trailLength, currentTime: t,
        }));
      }
      if (aircraftTrips.length) {
        // Keep the trail on the same altitude plane as the aircraft arrowhead.
        layers.push(new TripsLayer({
          id: "g-aircraft-trips", data: aircraftTrips,
          getPath: (d: Trip) => getAircraftDisplayPath(d, aircraftHeadAltitudesM) as [number, number, number][],
          getTimestamps: (d: Trip) => d.waypoints.map((w: TrackWaypoint) => w[2]),
          getColor: [255, 100, 50] as [number, number, number], opacity: 0.9,
          widthMinPixels: 3,
          capRounded: true,
          jointRounded: true,
          trailLength, currentTime: t,
        }));
      }
    }
    tripsLayersRef.current = layers;
    // Always include aircraft icon layers in the overlay update
    flushOverlay();
  }, [shipTrips, aircraftTrips, currentTime, trailLength, isAnimating]);

  // Entity position arrows on the globe (directional icons at track head)
  // Ships use MapLibre Symbol layer (2D), Aircraft use Deck.gl IconLayer (3D with altitude)
  useEffect(() => {
    const map = mapRef.current;
    const overlay = deckRef.current;
    if (!map || !overlay || !styleLoaded) return;
    const t = currentTime ?? Date.now() / 1000;

    if (!map.hasImage("ship-arrow")) map.addImage("ship-arrow", makeArrowImageData(20, 186, 140));  // Teal to match legend

    // MapLibre Symbol layer for ships (2D positioning at sea level)
    // Always visible regardless of animation state
    const shipPositions = computeEntityPositions(activeTrips.filter(t => t.entityType === "ship"), t);
    const src = map.getSource("g-entity-ships") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(shipPositions);
      const shipsVis = (showShipsLayer ?? true) ? "visible" : "none";
      if (map.getLayer("g-entity-ships")) map.setLayoutProperty("g-entity-ships", "visibility", shipsVis);
    } else {
      map.addSource("g-entity-ships", { type: "geojson", data: shipPositions });
      map.addLayer({
        id: "g-entity-ships", type: "symbol", source: "g-entity-ships",
        layout: {
          "icon-image": "ship-arrow",
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": 1.2,
        },
      });
    }

    // Deck.gl IconLayer for aircraft (3D positioning with altitude)
    // Always visible regardless of animation state
    const aircraftHeads = getTrackHeads(activeTrips.filter(t => t.entityType === "aircraft"), t);
    const aircraftIconLayers: any[] = [];
    if ((showAircraftLayer ?? true) && aircraftHeads.length > 0) {
      aircraftIconLayers.push(new IconLayer({
        id: "g-aircraft-icons",
        data: aircraftHeads,
        getPosition: (d) => [d.lng, d.lat, d.altitudeM || 0],  // 3D position at altitude
        getIcon: () => ({ url: "data:image/svg+xml;base64," + btoa(`
          <svg width="26" height="26" xmlns="http://www.w3.org/2000/svg">
            <polygon points="13,3 18,20 13,16 8,20" fill="rgb(255,220,50)" stroke="rgb(200,170,30)" stroke-width="1.5"/>
          </svg>
        `), width: 26, height: 26, anchorY: 13 }),
        getSize: 52,  // Doubled for visibility
        getAngle: (d) => -d.heading,  // Deck.gl rotates clockwise from north
        billboard: true,  // Keep the arrowhead facing the camera so it stays readable.
        sizeUnits: "pixels",
        pickable: true,
      }));
    }
    aircraftIconLayerRef.current = aircraftIconLayers;
    flushOverlay();
  }, [activeTrips, currentTime, showShipsLayer, showAircraftLayer, styleLoaded, isAnimating]);

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
          Number(p.lastSeenUnix ?? 0), lng, lat, Number(p.altitudeM ?? 0),
        ))
        .addTo(map);
    };
    const handleEventClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feat = e.features?.[0];
      if (!feat || feat.geometry.type !== "Point") return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates;
      const p = feat.properties as Record<string, unknown>;
      
      // Show analyst-useful information: title > headline > event type
      const displayTitle = String(p.title || p.headline || p.event_type || "Event").replace(/_/g, " ");
      const eventType = String(p.event_type || "").replace(/_/g, " ").toUpperCase();
      const eventTime = p.event_time ? new Date(String(p.event_time)).toLocaleString() : "—";
      const conf = p.confidence != null ? `${Math.round(Number(p.confidence) * 100)}%` : "—";
      const description = p.description ? String(p.description).slice(0, 200) : null;
      const url = p.url ? String(p.url) : null;
      
      let content = `<div class="entity-popup">
        <div class="entity-popup-header">⚡ INTEL EVENT</div>
        <div class="entity-popup-id">${displayTitle}</div>
        <div class="entity-popup-grid">
          <span class="ep-label">Type</span><span class="ep-val">${eventType}</span>
          <span class="ep-label">Time</span><span class="ep-val">${eventTime}</span>
          <span class="ep-label">Confidence</span><span class="ep-val">${conf}</span>`;
      
      if (description) {
        content += `<span class="ep-label">Details</span><span class="ep-val">${description}</span>`;
      }
      if (url) {
        content += `<span class="ep-label">Source</span><span class="ep-val"><a href="${url}" target="_blank" style="color:#00d4ff;">Link</a></span>`;
      }
      content += `</div></div>`;
      
      new maplibregl.Popup({ closeButton: true, maxWidth: "320px" })
        .setLngLat([lng, lat])
        .setHTML(content)
        .addTo(map);
    };
    const handleGdeltClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feat = e.features?.[0];
      if (!feat || feat.geometry.type !== "Point") return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates;
      const p = feat.properties as Record<string, unknown>;
      
      // Show analyst-useful information: headline, publication, URL
      const headline = String(p.headline || "News Article");
      const publication = p.source_publication ? String(p.source_publication) : null;
      const eventTime = p.date ? new Date(String(p.date)).toLocaleString() : "—";
      const conf = p.confidence != null ? `${Math.round(Number(p.confidence) * 100)}%` : "—";
      const url = p.url ? String(p.url) : null;
      
      let content = `<div class="entity-popup">
        <div class="entity-popup-header">📄 GDELT NEWS</div>
        <div class="entity-popup-id">${headline}</div>
        <div class="entity-popup-grid">
          <span class="ep-label">Time</span><span class="ep-val">${eventTime}</span>
          <span class="ep-label">Confidence</span><span class="ep-val">${conf}</span>`;
      
      if (publication) {
        content += `<span class="ep-label">Publication</span><span class="ep-val">${publication}</span>`;
      }
      if (url) {
        content += `<span class="ep-label">Source</span><span class="ep-val"><a href="${url}" target="_blank" style="color:#00d4ff;">Read Article</a></span>`;
      }
      content += `</div></div>`;
      
      new maplibregl.Popup({ closeButton: true, maxWidth: "320px" })
        .setLngLat([lng, lat])
        .setHTML(content)
        .addTo(map);
    };
    const handleSignalClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feat = e.features?.[0];
      if (!feat || feat.geometry.type !== "Point") return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates;
      const p = feat.properties as Record<string, unknown>;
      const label = String(p.type ?? "").replace(/_/g, " ").toUpperCase();
      const conf = p.confidence != null ? `${Math.round(Number(p.confidence) * 100)}%` : "\u2014";
      new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
        .setLngLat([lng, lat])
        .setHTML(`<div class="entity-popup"><div class="entity-popup-header">\u26a1 ${label}</div><div class="entity-popup-id">${String(p.id ?? "")}</div><div class="entity-popup-grid"><span class="ep-label">Source</span><span class="ep-val">${String(p.source ?? "\u2014")}</span><span class="ep-label">Confidence</span><span class="ep-val">${conf}</span></div></div>`)
        .addTo(map);
    };
    const handleDarkShipClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feat = e.features?.[0];
      if (!feat || feat.geometry.type !== "Point") return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates;
      const p = feat.properties as Record<string, unknown>;
      new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
        .setLngLat([lng, lat])
        .setHTML(`<div class="entity-popup entity-popup-ship"><div class="entity-popup-header">\uD83D\uDD26 DARK SHIP</div><div class="entity-popup-id">${String(p.label ?? "")}</div><div class="entity-popup-grid"><span class="ep-label">Confidence</span><span class="ep-val">${String(p.conf ?? "\u2014")}%</span></div></div>`)
        .addTo(map);
    };
    const cursorOn  = () => { map.getCanvas().style.cursor = "pointer"; };
    const cursorOff = () => { map.getCanvas().style.cursor = ""; };
    map.on("click",      "g-entity-ships",    handleEntityClick);
    map.on("click",      "g-entity-aircraft", handleEntityClick);
    map.on("click",      "g-events",          handleEventClick);
    map.on("click",      "g-gdelt",           handleGdeltClick);
    map.on("click",      "g-signals",         handleSignalClick);
    map.on("click",      "g-dark-ships",      handleDarkShipClick);
    map.on("mouseenter", "g-entity-ships",    cursorOn);
    map.on("mouseleave", "g-entity-ships",    cursorOff);
    map.on("mouseenter", "g-entity-aircraft", cursorOn);
    map.on("mouseleave", "g-entity-aircraft", cursorOff);
    map.on("mouseenter", "g-events",          cursorOn);
    map.on("mouseleave", "g-events",          cursorOff);
    map.on("mouseenter", "g-gdelt",           cursorOn);
    map.on("mouseleave", "g-gdelt",           cursorOff);
    map.on("mouseenter", "g-signals",         cursorOn);
    map.on("mouseleave", "g-signals",         cursorOff);
    map.on("mouseenter", "g-dark-ships",      cursorOn);
    map.on("mouseleave", "g-dark-ships",      cursorOff);
    return () => {
      map.off("click",      "g-entity-ships",    handleEntityClick);
      map.off("click",      "g-entity-aircraft", handleEntityClick);
      map.off("click",      "g-events",          handleEventClick);
      map.off("click",      "g-gdelt",           handleGdeltClick);
      map.off("click",      "g-signals",         handleSignalClick);
      map.off("click",      "g-dark-ships",      handleDarkShipClick);
      map.off("mouseenter", "g-entity-ships",    cursorOn);
      map.off("mouseleave", "g-entity-ships",    cursorOff);
      map.off("mouseenter", "g-entity-aircraft", cursorOn);
      map.off("mouseleave", "g-entity-aircraft", cursorOff);
      map.off("mouseenter", "g-events",          cursorOn);
      map.off("mouseleave", "g-events",          cursorOff);
      map.off("mouseenter", "g-gdelt",           cursorOn);
      map.off("mouseleave", "g-gdelt",           cursorOff);
      map.off("mouseenter", "g-signals",         cursorOn);
      map.off("mouseleave", "g-signals",         cursorOff);
      map.off("mouseenter", "g-dark-ships",      cursorOn);
      map.off("mouseleave", "g-dark-ships",      cursorOff);
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
      layout: { "text-field": ["get", "label"], "text-size": 11, "text-anchor": "center", "text-max-width": 10, "text-font": ["Noto Sans Regular"] },
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
          getColor: [100, 180, 255, 200] as [number, number, number, number],
          getWidth: 2,
          widthMinPixels: 1,
        })]
      : [];
    flushOverlay();
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

  // Jamming events — deck.gl ScatterplotLayer (radius in meters) - now clickable!
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
          pickable: true,
          onClick: (info) => {
            if (!info.object || !mapRef.current) return;
            const evt = info.object as GpsJammingEvent;
            new (maplibregl as typeof import('maplibre-gl')).Popup({ closeButton: true, maxWidth: "300px" })
              .setLngLat([evt.location_lon, evt.location_lat])
              .setHTML(`<div class="entity-popup">
                <div class="entity-popup-header">📡 GPS JAMMING</div>
                <div class="entity-popup-grid">
                  <span class="ep-label">Type</span><span class="ep-val">${evt.jamming_type}</span>
                  <span class="ep-label">Radius</span><span class="ep-val">${evt.radius_km ?? 50} km</span>
                  <span class="ep-label">Confidence</span><span class="ep-val">${Math.round(evt.confidence * 100)}%</span>
                  <span class="ep-label">Method</span><span class="ep-val">${evt.detection_method}</span>
                  <span class="ep-label">Detected</span><span class="ep-val">${new Date(evt.detected_at).toLocaleString()}</span>
                </div>
              </div>`)
              .addTo(mapRef.current);
            return true;
          },
        })]
      : [];
    flushOverlay();
  }, [showJammingLayer, jammingEvents]);

  // Track B — 3D Buildings via deck.gl Tile3DLayer
  // DISABLED: Google 3D Tiles API requires API key (403 Forbidden without VITE_3D_TILES_URL)
  useEffect(() => {
    const tile3dUrl = import.meta.env.VITE_3D_TILES_URL as string | undefined;
    // Only enable if explicit URL provided (no fallback to public Google API)
    buildingsLayerRef.current = (show3dBuildingsLayer && tile3dUrl)
      ? [new Tile3DLayer({
          id: "buildings-3d-tiles",
          data: tile3dUrl,
          opacity: 0.8,
          onTilesetLoad: () => {
            console.log('[GlobeView] 3D tiles loaded');
          },
          onTileError: (err) => {
            console.warn('[GlobeView] 3D tile error (non-fatal):', err);
          },
        })]
      : [];
    flushOverlay();
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
        "circle-color": ["match", ["get", "strike_type"],
          "airstrike", "#ff2200", "artillery", "#ff8800", "missile", "#ff0044", "drone", "#ff6600", "#ff9900",
        ] as unknown as string,
        // Double radius for selected strike; otherwise zoom-interpolated normal size.
        // ["zoom"] must be the top-level interpolate input — cannot nest inside ["*"].
        "circle-radius": ["interpolate", ["linear"], ["zoom"],
          1, ["case", ["==", ["get", "selected"], 1], 6, 3],
          6, ["case", ["==", ["get", "selected"], 1], ["*", ["get", "confidence"], 24], ["*", ["get", "confidence"], 12]],
        ] as unknown as number,
        "circle-opacity": 0.85,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1,
      },
    });
  }, [showStrikesLayer, strikeEvents, selectedEntityId, styleLoaded]);

  // Phase 4 Track D — AI detection overlay (deck.gl ScatterplotLayer) - now clickable!
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
          pickable: true,
          onClick: (info) => {
            if (!info.object || !mapRef.current) return;
            const det = info.object as DetectionOverlay;
            new (maplibregl as typeof import('maplibre-gl')).Popup({ closeButton: true, maxWidth: "300px" })
              .setLngLat([det.geo_location!.lon, det.geo_location!.lat])
              .setHTML(`<div class="entity-popup">
                <div class="entity-popup-header">🤖 AI DETECTION</div>
                <div class="entity-popup-grid">
                  <span class="ep-label">Type</span><span class="ep-val">${det.detection_type.replace(/_/g, ' ')}</span>
                  <span class="ep-label">Confidence</span><span class="ep-val">${Math.round(det.confidence * 100)}%</span>
                  <span class="ep-label">Source</span><span class="ep-val">${det.source}</span>
                  <span class="ep-label">Detected</span><span class="ep-val">${new Date(det.detected_at).toLocaleString()}</span>
                </div>
              </div>`)
              .addTo(mapRef.current);
            return true;
          },
        })]
      : [];
    flushOverlay();
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
    <div style={{ width: "100%", height: "100%", position: "relative", background: "#000000" }} data-testid="globe-container">
      <div
        ref={containerRef}
        className="globe-canvas-container"
        style={{
          width: "100%",
          height: "100%",
          filter: renderModeConfig.cssFilter,
          boxShadow: "0 0 120px 40px rgba(0, 212, 255, 0.08), inset 0 0 60px rgba(0, 0, 0, 0.4)",
        }}
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

