import { useState, useMemo, useEffect, useRef, Fragment } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { MapView } from "./components/Map/MapView";
import { GlobeView } from "./components/GlobeView/GlobeView";
import { AoiPanel } from "./components/AoiPanel/AoiPanel";
import { LayerPanel } from "./components/LayerPanel/LayerPanel";
import { TimelinePanel } from "./components/TimelinePanel/TimelinePanel";
import { SearchPanel } from "./components/SearchPanel/SearchPanel";
import { PlaybackPanel } from "./components/PlaybackPanel/PlaybackPanel";
import { AnalyticsPanel } from "./components/AnalyticsPanel/AnalyticsPanel";
import { ExportPanel } from "./components/ExportPanel/ExportPanel";
import { ImageryComparePanel } from "./components/ImageryComparePanel/ImageryComparePanel";
import { SystemHealthPage } from "./components/HealthDashboard/SystemHealthPage";
import { ChokepointPanel } from "./components/ChokepointPanel/ChokepointPanel";
import { DarkShipPanel } from "./components/DarkShipPanel/DarkShipPanel";
import { IntelBriefingPanel } from "./components/IntelBriefingPanel/IntelBriefingPanel";
import { CameraFeedPanel } from "./components/CameraFeedPanel/CameraFeedPanel";
import { VesselProfileModal } from "./components/VesselProfileModal/VesselProfileModal";
import { InvestigationsPanel } from "./components/InvestigationsPanel/InvestigationsPanel";
import { ChokeMetricsBar } from "./components/ChokeMetricsBar/ChokeMetricsBar";
import { useImagerySearch } from "./hooks/useImagery";
import { useEventSearch } from "./hooks/useEvents";
import { useTracks } from "./hooks/useTracks";
import { useAois } from "./hooks/useAois";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { useOrbits, useAirspaceRestrictions, useJammingLayer, useStrikeLayer, useAllSatellitePasses } from "./hooks/useOperationalLayers";
import { useDetectionLayer } from "./hooks/useCameras";
import { useTimelineSync } from "./components/TimelinePanel/useTimelineSync";
import { useRenderMode } from "./hooks/useRenderMode";
import { RenderModeSelector } from "./components/RenderModeSelector/RenderModeSelector";
import { subDays } from "date-fns";
import type { CanonicalEvent } from "./api/types";
import "./App.css";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

// Stable module-level constants — defined outside the component so they are never recreated on render.
const SIGNAL_EVENT_TYPES: import("./api/types").EventType[] = [
  "seismic_event", "natural_hazard_event", "weather_observation",
  "conflict_event", "maritime_warning", "military_site_observation",
  "thermal_anomaly_event", "space_weather_event", "air_quality_observation",
];
const CORE_EVENT_TYPES: import("./api/types").EventType[] = [
  "permit_event", "inspection_event", "project_event", "complaint_event",
];

/**
 * Minimum ms between React state updates during track animation.
 * ~20 fps is intentionally used to keep replay smooth under headless recording
 * and heavy map rendering loads (prevents narration/video desync).
 */
const ANIM_FRAME_MS = 50;

// ── Event detail helpers ─────────────────────────────────────────────────────
function formatEventType(et: string): string {
  const labels: Record<string, string> = {
    ship_position: "Vessel Position",
    ship_track_segment: "Vessel Track Segment",
    dark_ship_candidate: "Dark Vessel Alert",
    aircraft_position: "Aircraft Position",
    aircraft_track_segment: "Aircraft Track Segment",
    imagery_acquisition: "Imagery Acquisition",
    imagery_detection: "Imagery Detection",
    change_detection: "Change Detection",
    contextual_event: "News / Context",
    seismic_event: "Seismic Event",
    natural_hazard_event: "Natural Hazard",
    weather_observation: "Weather Observation",
    conflict_event: "Conflict Incident",
    maritime_warning: "Maritime Warning",
    military_site_observation: "Military Site Observation",
    thermal_anomaly_event: "Thermal Anomaly / Fire",
    space_weather_event: "Space Weather Alert",
    air_quality_observation: "Air Quality Reading",
    permit_event: "Permit",
    inspection_event: "Inspection",
    project_event: "Project",
    complaint_event: "Complaint",
  };
  return labels[et] ?? et.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

function eventTypeIcon(et: string): string {
  const icons: Record<string, string> = {
    ship_position: "🚢", ship_track_segment: "🚢", dark_ship_candidate: "⚠️",
    aircraft_position: "✈️", aircraft_track_segment: "✈️",
    imagery_acquisition: "🛰️", imagery_detection: "🔍", change_detection: "🔄",
    contextual_event: "📰", seismic_event: "🌍", natural_hazard_event: "⚠️",
    conflict_event: "⚔️", weather_observation: "🌤️", maritime_warning: "⚓",
    military_site_observation: "🎯", thermal_anomaly_event: "🔥",
    space_weather_event: "☀️", air_quality_observation: "💨",
    permit_event: "📋", inspection_event: "🔎", project_event: "🏗️", complaint_event: "📣",
  };
  return icons[et] ?? "📍";
}

function buildEventRows(evt: CanonicalEvent): Array<[string, string]> {
  const attrs = (evt.attributes ?? {}) as Record<string, unknown>;
  const rows: Array<[string, string]> = [];
  const s = (v: unknown) => String(v ?? "").trim();
  const n = (v: unknown) => Number(v);

  switch (evt.event_type) {
    case "ship_position":
    case "ship_track_segment":
    case "dark_ship_candidate":
      if (attrs.vessel_name) rows.push(["Vessel", s(attrs.vessel_name)]);
      if (attrs.mmsi) rows.push(["MMSI", s(attrs.mmsi)]);
      if (attrs.nav_status) rows.push(["Nav Status", s(attrs.nav_status)]);
      if (attrs.speed_kn != null) rows.push(["Speed", `${n(attrs.speed_kn).toFixed(1)} kn`]);
      if (attrs.course_deg != null) rows.push(["Course", `${n(attrs.course_deg).toFixed(0)}°`]);
      if (attrs.destination) rows.push(["Destination", s(attrs.destination)]);
      if (attrs.eta) rows.push(["ETA", s(attrs.eta)]);
      break;
    case "aircraft_position":
    case "aircraft_track_segment":
      if (attrs.callsign) rows.push(["Callsign", s(attrs.callsign)]);
      if (attrs.icao24) rows.push(["ICAO24", s(attrs.icao24)]);
      if (attrs.origin_country) rows.push(["Origin", s(attrs.origin_country)]);
      if (attrs.baro_altitude_m != null) rows.push(["Altitude", `${Math.round(n(attrs.baro_altitude_m))} m`]);
      if (attrs.velocity_ms != null) rows.push(["Speed", `${Math.round(n(attrs.velocity_ms) * 1.944)} kn`]);
      if (attrs.on_ground != null) rows.push(["On Ground", attrs.on_ground ? "Yes" : "No"]);
      break;
    case "contextual_event":
      if (attrs.headline) rows.push(["Headline", s(attrs.headline)]);
      if (attrs.source_publication) rows.push(["Publication", s(attrs.source_publication)]);
      if (attrs.tone != null) rows.push(["Sentiment", n(attrs.tone) >= 0 ? `+${n(attrs.tone).toFixed(1)}` : n(attrs.tone).toFixed(1)]);
      if (attrs.num_mentions != null) rows.push(["Mentions", s(attrs.num_mentions)]);
      break;
    case "seismic_event":
      if (attrs.place) rows.push(["Location", s(attrs.place)]);
      if (attrs.magnitude != null) rows.push(["Magnitude", `M${n(attrs.magnitude).toFixed(1)} ${s(attrs.magnitude_type)}`]);
      if (attrs.depth_km != null) rows.push(["Depth", `${n(attrs.depth_km).toFixed(1)} km`]);
      if (attrs.alert) rows.push(["Alert Level", s(attrs.alert)]);
      if (attrs.tsunami_flag) rows.push(["Tsunami Warning", "Yes"]);
      break;
    case "natural_hazard_event":
      if (attrs.category_title) rows.push(["Category", s(attrs.category_title)]);
      if (attrs.status) rows.push(["Status", s(attrs.status)]);
      break;
    case "weather_observation":
      if (attrs.temperature_c != null) rows.push(["Temperature", `${n(attrs.temperature_c).toFixed(1)} °C`]);
      if (attrs.cloud_cover_pct != null) rows.push(["Cloud Cover", `${n(attrs.cloud_cover_pct).toFixed(0)}%`]);
      if (attrs.wind_speed_ms != null) rows.push(["Wind Speed", `${n(attrs.wind_speed_ms).toFixed(1)} m/s`]);
      if (attrs.precipitation_mm != null) rows.push(["Precipitation", `${n(attrs.precipitation_mm).toFixed(1)} mm`]);
      break;
    case "conflict_event":
      if (attrs.country) rows.push(["Country", s(attrs.country)]);
      if (attrs.location) rows.push(["Location", s(attrs.location)]);
      if (attrs.disorder_type) rows.push(["Type", s(attrs.disorder_type)]);
      if (attrs.actor1) rows.push(["Actor 1", s(attrs.actor1)]);
      if (attrs.actor2) rows.push(["Actor 2", s(attrs.actor2)]);
      if (attrs.fatalities != null) rows.push(["Fatalities", s(attrs.fatalities)]);
      if (attrs.notes) rows.push(["Notes", s(attrs.notes).slice(0, 220)]);
      break;
    case "maritime_warning":
      if (attrs.authority) rows.push(["Authority", s(attrs.authority)]);
      if (attrs.nav_area) rows.push(["Nav Area", s(attrs.nav_area)]);
      if (attrs.status) rows.push(["Status", s(attrs.status)]);
      if (attrs.warning_text) rows.push(["Warning", s(attrs.warning_text).slice(0, 300)]);
      if (attrs.cancel_date) rows.push(["Cancels", s(attrs.cancel_date)]);
      break;
    case "military_site_observation":
      if (attrs.name) rows.push(["Site Name", s(attrs.name)]);
      if (attrs.military_type) rows.push(["Site Type", s(attrs.military_type)]);
      if (attrs.operator) rows.push(["Operator", s(attrs.operator)]);
      break;
    case "thermal_anomaly_event":
      if (attrs.satellite) rows.push(["Satellite", s(attrs.satellite)]);
      if (attrs.instrument) rows.push(["Instrument", s(attrs.instrument)]);
      if (attrs.frp != null) rows.push(["Fire Radiative Power", `${n(attrs.frp).toFixed(1)} MW`]);
      if (attrs.brightness != null) rows.push(["Brightness Temp", `${n(attrs.brightness).toFixed(0)} K`]);
      if (attrs.day_night) rows.push(["Acquisition", attrs.day_night === "D" ? "Daytime" : "Nighttime"]);
      if (attrs.source_dataset) rows.push(["Dataset", s(attrs.source_dataset)]);
      break;
    case "space_weather_event":
      if (attrs.phenomenon) rows.push(["Phenomenon", s(attrs.phenomenon)]);
      if (attrs.noaa_scale) rows.push(["NOAA Scale", s(attrs.noaa_scale)]);
      if (attrs.severity) rows.push(["Severity", s(attrs.severity)]);
      if (attrs.kp_index != null) rows.push(["Kp Index", s(attrs.kp_index)]);
      if (attrs.message) rows.push(["Alert", s(attrs.message).slice(0, 250)]);
      break;
    case "air_quality_observation":
      if (attrs.location_name) rows.push(["Station", s(attrs.location_name)]);
      if (attrs.display_name ?? attrs.parameter) rows.push(["Parameter", s(attrs.display_name ?? attrs.parameter)]);
      if (attrs.value != null) rows.push(["Reading", s(attrs.unit) ? `${attrs.value} ${s(attrs.unit)}` : s(attrs.value)]);
      break;
    case "permit_event":
    case "inspection_event":
    case "project_event":
    case "complaint_event":
      if (attrs.permit_number) rows.push(["Permit #", s(attrs.permit_number)]);
      if (attrs.applicant) rows.push(["Applicant", s(attrs.applicant)]);
      if (attrs.permit_type) rows.push(["Permit Type", s(attrs.permit_type)]);
      if (attrs.status) rows.push(["Status", s(attrs.status)]);
      if (attrs.description) rows.push(["Description", s(attrs.description).slice(0, 200)]);
      if (attrs.authority) rows.push(["Authority", s(attrs.authority)]);
      break;
    case "imagery_acquisition":
    case "imagery_detection":
    case "change_detection":
      if (attrs.platform) rows.push(["Platform", s(attrs.platform)]);
      if (attrs.sensor) rows.push(["Sensor", s(attrs.sensor)]);
      if (attrs.gsd_m != null) rows.push(["Resolution", `${n(attrs.gsd_m)} m GSD`]);
      if (attrs.cloud_cover_pct != null) rows.push(["Cloud Cover", `${n(attrs.cloud_cover_pct).toFixed(0)}%`]);
      if (attrs.processing_level) rows.push(["Processing Level", s(attrs.processing_level)]);
      break;
  }
  return rows.filter(([, v]) => v !== "");
}

const MAP_STYLE_OPTIONS = [
  { id: "vector",    label: "Vector",    bg: "#0c1a2e" },
  { id: "dark",      label: "Dark",      bg: "#111111" },
  { id: "light",     label: "Light",     bg: "#d4d8dd" },
  { id: "satellite", label: "Sat",       bg: "#1a3020" },
] as const;

function AppShell() {
  const { apiKey, setApiKey } = useAuth();
  const [selectedAoiId, setSelectedAoiId] = useLocalStorage<string | null>("selectedAoiId", null);
  const [drawMode, setDrawMode] = useState<"none" | "polygon" | "bbox">("none");
  const [pendingGeometry, setPendingGeometry] = useState<GeoJSON.Geometry | null>(null);
  const [startTime, setStartTime] = useState<string>(subDays(new Date(), 30).toISOString());
  const [endTime, setEndTime] = useState<string>(new Date().toISOString());
  const [selectedEvent, setSelectedEvent] = useState<CanonicalEvent | null>(null);
  const [activePanel, setActivePanel] = useLocalStorage<string>("activePanel", "aoi");
  // P2-5.3: 2D/3D view-mode toggle
  const [viewMode, setViewMode] = useLocalStorage<"2d" | "3d">("viewMode", "3d");
  const [mapSettings, setMapSettings] = useLocalStorage("mapSettings", { baseStyle: "vector" });
  // Phase 4 Track A — render modes
  const { mode: renderMode, setMode: setRenderMode } = useRenderMode();
  // Phase 4 Track B — camera feed panel focus
  const [cameraFocusPoint, setCameraFocusPoint] = useState<{ lon: number; lat: number } | null>(null);
  // Phase 4 Track C — shared entity selection
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [isGlobeBriefingExpanded, setIsGlobeBriefingExpanded] = useState(false);

  // Track animation: null = live end-of-range, number = Unix seconds sim time
  const [playbackTime, setPlaybackTime] = useState<number | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const animRafRef = useRef<number | null>(null);
  // Tracks last wall-clock time a React state update was issued to throttle to ~30fps.
  const lastAnimStateRef = useRef<number>(0);
  const ANIM_SPEED_RATIO = 3600; // 1 real second = 1 simulated hour

  // Smooth rAF animation loop — advances simulation time from startTime to endTime.
  // setPlaybackTime is throttled to ANIM_FRAME_MS (~30fps) to avoid 60fps component
  // re-renders cascading through the entire AppShell tree.
  useEffect(() => {
    if (!isAnimating) {
      if (animRafRef.current !== null) { cancelAnimationFrame(animRafRef.current); animRafRef.current = null; }
      return;
    }
    const simEnd = Date.parse(endTime) / 1000;
    const simStart = playbackTime ?? trackAnimationStartTime;
    const realStart = performance.now();
    function tick(now: number) {
      const elapsed = (now - realStart) / 1000;
      const next = simStart + elapsed * ANIM_SPEED_RATIO;
      if (next >= simEnd) { setPlaybackTime(simEnd); setIsAnimating(false); return; }
      // Only push to React state at ~30fps — rAF keeps running for accurate timing.
      if (now - lastAnimStateRef.current >= ANIM_FRAME_MS) {
        lastAnimStateRef.current = now;
        setPlaybackTime(next);
      }
      animRafRef.current = requestAnimationFrame(tick);
    }
    animRafRef.current = requestAnimationFrame(tick);
    return () => { if (animRafRef.current !== null) { cancelAnimationFrame(animRafRef.current); animRafRef.current = null; } };
  }, [isAnimating]); // eslint-disable-line react-hooks/exhaustive-deps
  const [layers, setLayers] = useLocalStorage("layers", {
    showAois: true, showImagery: true, showEvents: true,
    showGdelt: true, showShips: true, showAircraft: true,
    trackDensity: 1.0,
    // P2-3.3: imagery footprint opacity
    imageryOpacity: 0.1,
    showOrbits: false,
    showAirspace: false,
    showJamming: false,
    showStrikes: false,
    showTerrain: false,
    show3dBuildings: false,
    showDetections: false,
    showSignals: true,
  });

  // P2-5.2: fetch all AOIs to render on globe
  const aoiQuery = useAois();
  // useMemo avoids a new [] reference on every render when data is undefined.
  const aois = useMemo(() => aoiQuery.data ?? [], [aoiQuery.data]);

  // Auto-select first AOI when available and nothing is selected.
  // Also recover from stale persisted AOI ids after backend/demo restarts,
  // where the in-memory AOI UUID can change.
  // Use aoiQuery.data as the dep so the stable query-result reference is tracked,
  // not the inline `?? []` fallback which creates a new array every render.
  useEffect(() => {
    const list = aoiQuery.data;
    const hasSelection = !!selectedAoiId;
    const selectionExists = hasSelection && !!list?.some(a => a.id === selectedAoiId);
    if (list && list.length > 0 && (!hasSelection || !selectionExists)) {
      setSelectedAoiId(list[0].id);
    }
  }, [aoiQuery.data, selectedAoiId, setSelectedAoiId]);

  const selectedAoi = aois.find(a => a.id === selectedAoiId);
  const imagerySearch = useImagerySearch(selectedAoi ? {
    geometry: selectedAoi.geometry,
    start_time: startTime,
    end_time: endTime,
    cloud_threshold: 30,
  } : null);

  // P2-1.5/1.6: Fetch GDELT contextual events when layer is enabled
  const gdeltSearch = useEventSearch(
    layers.showGdelt && selectedAoiId
      ? { aoi_id: selectedAoiId, start_time: startTime, end_time: endTime, source_types: ["context_feed"], limit: 300 }
      : null
  );
  const coreEventSearch = useEventSearch(
    layers.showEvents && selectedAoiId
      ? { aoi_id: selectedAoiId, start_time: startTime, end_time: endTime, event_types: CORE_EVENT_TYPES, limit: 250 }
      : null
  );

  // Fetch all intelligence signal events — SIGNAL_EVENT_TYPES is module-level (stable reference).
  const signalsSearch = useEventSearch(
    layers.showSignals && selectedAoiId
      ? { aoi_id: selectedAoiId, start_time: startTime, end_time: endTime, event_types: SIGNAL_EVENT_TYPES, limit: 500 }
      : null
  );

  // Phase 2 operational layers
  const orbitsQuery = useOrbits();
  const airspaceQuery = useAirspaceRestrictions(true);
  const jammingQuery = useJammingLayer();
  const strikesQuery = useStrikeLayer();
  // Phase 4 Track D — AI detection overlays
  const detectionsQuery = useDetectionLayer();

  // Timeline filtering — keeps MapView and GlobeView temporally consistent
  const { setCurrentTime, currentTimeUnix, filteredJammingEvents, filteredStrikes, filteredAirspaceRestrictions } = useTimelineSync();
  useEffect(() => {
    setCurrentTime(playbackTime ? new Date(playbackTime * 1000) : new Date(endTime));
  }, [playbackTime, endTime]); // eslint-disable-line react-hooks/exhaustive-deps

  // Derive AOI center for satellite pass queries
  const aoiCenter = useMemo(() => {
    if (!selectedAoi?.geometry) return { lon: 0, lat: 0 };
    const geom = selectedAoi.geometry as GeoJSON.Geometry;
    if (geom.type === "Point") return { lon: (geom as GeoJSON.Point).coordinates[0], lat: (geom as GeoJSON.Point).coordinates[1] };
    if (geom.type === "Polygon") return { lon: (geom as GeoJSON.Polygon).coordinates[0][0][0], lat: (geom as GeoJSON.Polygon).coordinates[0][0][1] };
    return { lon: 0, lat: 0 };
  }, [selectedAoi]);

  // Stable array reference: prevents useAllSatellitePasses from re-fetching every render
  // when orbitsQuery.orbits is undefined (inline ?? [] creates a new array each time).
  const orbits = useMemo(() => orbitsQuery.orbits ?? [], [orbitsQuery.orbits]);
  const passesQuery = useAllSatellitePasses(orbits, aoiCenter.lon, aoiCenter.lat, 24);

  // P3-3.2/3.3: Fetch entity tracks when maritime or aviation layer is enabled
  const tracksQuery = useTracks(
    selectedAoiId,
    startTime,
    endTime,
    layers.showShips || layers.showAircraft,
  );

  // P3-3.6: Subsample tracks by density slider value
  const visibleTracks = useMemo(() => {
    const all = tracksQuery.data ?? [];
    if (layers.trackDensity >= 1) return all;
    const step = Math.round(1 / layers.trackDensity);
    return all.filter((_, i) => i % step === 0);
  }, [tracksQuery.data, layers.trackDensity]);
  const trackAnimationStartTime = useMemo(() => {
    const fallback = Date.parse(startTime) / 1000;
    let earliestTrackPoint = Number.POSITIVE_INFINITY;
    for (const trip of visibleTracks) {
      const firstPoint = trip.waypoints[0]?.[2];
      if (firstPoint != null) earliestTrackPoint = Math.min(earliestTrackPoint, firstPoint);
    }
    if (!Number.isFinite(earliestTrackPoint)) return fallback;
    return Math.max(fallback, earliestTrackPoint - 900);
  }, [startTime, visibleTracks]);

  // currentTime for TripsLayer — driven by animation or playback, fallback to end of window
  const tracksCurrentTime = playbackTime ?? (Date.parse(endTime) / 1000);
  // Keep only very recent tails visible to prevent map-spanning artifacts
  // during high-speed replay.
  const tracksTrailLength = 5 * 60;

  // ── Memoize all layer data arrays ─────────────────────────────────────────
  // Each `?? []` fallback would create a new array reference on every render,
  // causing MapView/GlobeView effects (setData, setProps) to run unnecessarily.
  const coreEventData   = useMemo(() => coreEventSearch.data ?? [], [coreEventSearch.data]);
  const gdeltData       = useMemo(() => gdeltSearch.data ?? [], [gdeltSearch.data]);
  const imageryData     = useMemo(() => imagerySearch.data ?? [], [imagerySearch.data]);
  const orbitPassData   = useMemo(() => passesQuery.passes ?? [], [passesQuery.passes]);
  const detectionsData  = useMemo(() => detectionsQuery.detections ?? [], [detectionsQuery.detections]);
  const signalData      = useMemo(() => signalsSearch.data ?? [], [signalsSearch.data]);
  const jammingRaw      = useMemo(() => jammingQuery.events ?? [], [jammingQuery.events]);
  const strikesRaw      = useMemo(() => strikesQuery.strikes ?? [], [strikesQuery.strikes]);
  const airspaceRaw     = useMemo(() => airspaceQuery.restrictions ?? [], [airspaceQuery.restrictions]);
  // Pre-apply timeline filter once per render — avoids calling the filter function twice
  // (MapView + GlobeView) with a new array result each time.
  const jammingFiltered   = useMemo(() => filteredJammingEvents(jammingRaw),   [filteredJammingEvents, jammingRaw]);
  const strikesFiltered   = useMemo(() => filteredStrikes(strikesRaw),         [filteredStrikes, strikesRaw]);
  const airspaceFiltered  = useMemo(() => filteredAirspaceRestrictions(airspaceRaw), [filteredAirspaceRestrictions, airspaceRaw]);

  const [selectedVesselMmsi, setSelectedVesselMmsi] = useState<string | null>(null);

  const PANELS = [
    { key: "aoi", label: "Zones", icon: "⬡" },
    { key: "layers", label: "Sensors", icon: "📡" },
    { key: "search", label: "Signals", icon: "⚡" },
    { key: "playback", label: "Replay", icon: "▶" },
    { key: "analytics", label: "Intel", icon: "◈" },
    { key: "chokepoints", label: "Routes", icon: "⚓" },
    { key: "darkships", label: "Dark Ships", icon: "🔦" },
    { key: "intelbrief", label: "Briefing", icon: "🛡" },
    { key: "export", label: "Extract", icon: "↓" },
    { key: "compare", label: "Diff", icon: "⊟" },
    { key: "cameras", label: "Cameras", icon: "📷" },
    { key: "health", label: "Status", icon: "◉" },
    { key: "investigations", label: "Cases", icon: "🔍" },
  ];

  const [clock, setClock] = useState(() => new Date().toUTCString().slice(17, 25));
  useEffect(() => {
    const t = setInterval(() => setClock(new Date().toUTCString().slice(17, 25)), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-title">
          <div className="argus-logo">
            <div className="argus-ring" />
            <div className="argus-ring argus-ring--2" />
            <div className="argus-core" />
          </div>
          <div>
            <h1>ARGUS</h1>
            <span className="app-subtitle">Maritime Intelligence Platform</span>
          </div>
        </div>
        <div className="header-center">
          <span className="live-badge">● LIVE</span>
          <span className="header-clock">{clock} UTC</span>
        </div>
        <div className="header-controls">
          <input
            type="password"
            placeholder="API Key (optional)"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            className="input-sm api-key-input"
            title="API key for authenticated endpoints"
          />
        </div>
      </header>
      <div className="app-body">
        <nav className="sidebar">
          {PANELS.map(p => (
            <button
              key={p.key}
              className={`sidebar-btn ${activePanel === p.key ? "sidebar-btn--active" : ""}`}
              onClick={() => setActivePanel(p.key)}
            >
              <span className="sidebar-icon">{p.icon}</span>
              <span className="sidebar-label">{p.label}</span>
            </button>
          ))}
        </nav>
        <div className="side-panel">
          {activePanel === "aoi" && (
            <AoiPanel
              selectedAoiId={selectedAoiId}
              onSelect={setSelectedAoiId}
              drawMode={drawMode}
              onDrawModeChange={setDrawMode}
              pendingGeometry={pendingGeometry}
              onClearPendingGeometry={() => setPendingGeometry(null)}
            />
          )}
          {activePanel === "layers" && <LayerPanel layers={layers} onChange={setLayers} />}
          {activePanel === "search" && (
            <SearchPanel
              aoiId={selectedAoiId}
              startTime={startTime}
              endTime={endTime}
              onEventSelect={setSelectedEvent}
            />
          )}
          {activePanel === "playback" && (
            <PlaybackPanel
              aoiId={selectedAoiId}
              startTime={startTime}
              endTime={endTime}
              onFrameChange={frame => {
                if (frame) {
                  const t = new Date(frame.event.event_time).getTime() / 1000;
                  if (!isNaN(t)) { setIsAnimating(false); setPlaybackTime(t); }
                }
              }}
            />
          )}
          {activePanel === "analytics" && <AnalyticsPanel aoiId={selectedAoiId} startTime={startTime} endTime={endTime} />}
          {activePanel === "chokepoints" && (
            <ChokepointPanel onChokepointSelect={id => { void id; }} />
          )}
          {activePanel === "darkships" && (
            <DarkShipPanel onCandidateSelect={c => c.mmsi ? setSelectedVesselMmsi(c.mmsi) : undefined} />
          )}
          {activePanel === "intelbrief" && (
            <IntelBriefingPanel onVesselSelect={setSelectedVesselMmsi} />
          )}
          {activePanel === "cameras" && (
            <CameraFeedPanel
              onJumpToLocation={(lon, lat) => setCameraFocusPoint({ lon, lat })}
              currentTime={currentTimeUnix}
            />
          )}
          {activePanel === "export" && (
            <ExportPanel aoiId={selectedAoiId} startTime={startTime} endTime={endTime} />
          )}
          {/* P2-3.2: before/after imagery compare panel */}
          {activePanel === "compare" && (
            <ImageryComparePanel items={imageryData} />
          )}
          {/* Phase 5: Investigation workflow panel */}
          {activePanel === "investigations" && (
            <InvestigationsPanel visible={activePanel === "investigations"} />
          )}
        </div>
        <div className={`map-area${activePanel === "health" ? " map-area--health" : ""}`}>
          {/* Health monitoring full-canvas page */}
          {activePanel === "health" && <SystemHealthPage />}
          {activePanel !== "health" && (
            <>
          <div className="view-mode-toggle">
            <button
              className={`btn btn-xs ${viewMode === "2d" ? "btn-active" : ""}`}
              onClick={() => setViewMode("2d")}
              title="2D map view"
            >2D</button>
            <button
              className={`btn btn-xs ${viewMode === "3d" ? "btn-active" : ""}`}
              onClick={() => setViewMode("3d")}
              title="3D globe view"
            >🌐 3D</button>
          </div>
          <div style={{ display: "flex", alignItems: "center", position: "absolute", top: 8, left: "50%", transform: "translateX(-50%)", zIndex: 10, pointerEvents: "auto" }}>
            <RenderModeSelector mode={renderMode} onModeChange={setRenderMode} />
          </div>

          {/* Animation controls */}
          <div className="anim-controls">
            <button
              className={`btn btn-xs ${isAnimating ? "btn-active" : ""}`}
              onClick={() => setIsAnimating(v => !v)}
              title={isAnimating ? "Pause" : "Animate tracks through time range"}
            >{isAnimating ? "⏸" : "▶"}</button>
            <button
              className="btn btn-xs"
              onClick={() => { setIsAnimating(false); setPlaybackTime(null); }}
              title="Reset to end of range"
            >↺</button>
            {playbackTime !== null && (
              <span className="anim-time">
                {new Date(playbackTime * 1000).toISOString().slice(0, 16).replace("T", " ")}Z
              </span>
            )}
          </div>

          {/* Map-surface draw tools — always visible in 2D so users can draw AOIs directly */}
          {viewMode === "2d" && (
            <div className="map-draw-tools">
              <button
                className={`btn btn-xs ${drawMode === "bbox" ? "btn-active" : ""}`}
                onClick={() => setDrawMode(drawMode === "bbox" ? "none" : "bbox")}
                title="Draw bounding box — click 2 opposite corners on the map"
              >⬜ BBox</button>
              <button
                className={`btn btn-xs ${drawMode === "polygon" ? "btn-active" : ""}`}
                onClick={() => setDrawMode(drawMode === "polygon" ? "none" : "polygon")}
                title="Draw polygon — click vertices, double-click to close"
              >⬡ Polygon</button>
              {drawMode !== "none" && (
                <span className="draw-hint">
                  {drawMode === "bbox" ? "Click 2 corners on the map" : "Click vertices, double-click to finish"}
                </span>
              )}
            </div>
          )}

          {/* P2-3.3: imagery opacity slider shown in 2D mode */}
          {viewMode === "2d" && layers.showImagery && (
            <div className="imagery-opacity-ctrl">
              <label className="label-sm">Imagery opacity</label>
              <input
                type="range" min="0" max="1" step="0.05"
                value={layers.imageryOpacity}
                onChange={e => setLayers(l => ({ ...l, imageryOpacity: Number(e.target.value) }))}
                className="opacity-slider"
                title={`Imagery opacity: ${Math.round(layers.imageryOpacity * 100)}%`}
              />
              <span className="label-sm">{Math.round(layers.imageryOpacity * 100)}%</span>
            </div>
          )}

          {/* Basemap style picker — only in 2D (globe ignores baseStyle) */}
          {viewMode === "2d" && (
            <div className="basemap-picker">
              {MAP_STYLE_OPTIONS.map(s => (
                <button
                  key={s.id}
                  className={`basemap-btn${mapSettings.baseStyle === s.id ? " basemap-btn--active" : ""}`}
                  onClick={() => setMapSettings(prev => ({ ...prev, baseStyle: s.id }))}
                  title={`Base map: ${s.label}`}
                >
                  <span className="basemap-swatch" style={{ background: s.bg }} />
                  <span>{s.label}</span>
                </button>
              ))}
            </div>
          )}

          {viewMode === "2d" ? (
            <MapView
              aois={aois}
              imageryItems={imageryData}
              events={coreEventData}
              drawMode={drawMode}
              selectedAoiId={selectedAoiId}
              onAoiClick={setSelectedAoiId}
              onAoiDraw={geom => { setPendingGeometry(geom); setDrawMode("none"); }}
              onEventClick={setSelectedEvent}
              showImageryLayer={layers.showImagery}
              showEventLayer={layers.showEvents}
              gdeltEvents={gdeltData}
              showGdeltLayer={layers.showGdelt}
              imageryOpacity={layers.imageryOpacity}
              trips={visibleTracks}
              currentTime={tracksCurrentTime}
              trailLength={tracksTrailLength}
              showShipsLayer={layers.showShips}
              showAircraftLayer={layers.showAircraft}
              baseStyle={mapSettings.baseStyle}
              showOrbitsLayer={layers.showOrbits}
              orbitPasses={orbitPassData}
              showAirspaceLayer={layers.showAirspace}
              airspaceRestrictions={airspaceFiltered}
              showJammingLayer={layers.showJamming}
              jammingEvents={jammingFiltered}
              showStrikesLayer={layers.showStrikes}
              strikeEvents={strikesFiltered}
              showDetectionsLayer={layers.showDetections}
              detections={detectionsData}
              signalEvents={signalData}
              showSignalsLayer={layers.showSignals}
              renderMode={renderMode}
              onStrikeClick={(id) => setSelectedEntityId(id)}
              centerPoint={cameraFocusPoint ?? undefined}
            />
          ) : (
            /* P2-5.1/5.2: globe.gl 3D overview */
            <>
              <GlobeView
                aois={aois}
                events={coreEventData}
                gdeltEvents={gdeltData}
                trips={visibleTracks}
                showEventLayer={layers.showEvents}
                showGdeltLayer={layers.showGdelt}
                showShipsLayer={layers.showShips}
                showAircraftLayer={layers.showAircraft}
                currentTime={tracksCurrentTime}
                trailLength={tracksTrailLength}
                showOrbitsLayer={layers.showOrbits}
                orbitPasses={orbitPassData}
                showAirspaceLayer={layers.showAirspace}
                airspaceRestrictions={airspaceFiltered}
                showJammingLayer={layers.showJamming}
                jammingEvents={jammingFiltered}
                showStrikesLayer={layers.showStrikes}
                strikeEvents={strikesFiltered}
                showTerrainLayer={layers.showTerrain}
                show3dBuildingsLayer={layers.show3dBuildings}
                showDetectionsLayer={layers.showDetections}
                detections={detectionsData}
                signalEvents={signalData}
                showSignalsLayer={layers.showSignals}
                renderMode={renderMode}
                selectedEntityId={selectedEntityId}
                centerPoint={cameraFocusPoint ?? undefined}
              />
              {/* P6: Intel briefing overlay (top-right of globe) */}
              <div className={`globe-intel-overlay${isGlobeBriefingExpanded ? " globe-intel-overlay--expanded" : " globe-intel-overlay--collapsed"}`}>
                <button
                  type="button"
                  className="globe-intel-toggle"
                  onClick={() => setIsGlobeBriefingExpanded(v => !v)}
                  aria-expanded={isGlobeBriefingExpanded}
                  title={isGlobeBriefingExpanded ? "Collapse globe briefing" : "Expand globe briefing"}
                >
                  <span className="globe-intel-toggle-label">INTEL BRIEFING</span>
                  <span className="globe-intel-toggle-icon">{isGlobeBriefingExpanded ? "−" : "+"}</span>
                </button>
                {isGlobeBriefingExpanded && (
                  <IntelBriefingPanel compact={true} />
                )}
              </div>
              {/* P6-8: Chokepoint metrics bar at bottom of globe */}
              <ChokeMetricsBar />
            </>
          )}
            </>
          )}
        </div>
      </div>
      <div className="timeline-bar">
        <TimelinePanel
          aoiId={selectedAoiId}
          startTime={startTime}
          endTime={endTime}
          onRangeChange={(s, e) => { setStartTime(s); setEndTime(e); }}
          onTimeSeek={isoTime => {
            setIsAnimating(false);
            setPlaybackTime(Date.parse(isoTime) / 1000);
          }}
        />
      </div>
      {/* P6: Vessel profile modal */}
      {selectedVesselMmsi && (
        <VesselProfileModal mmsi={selectedVesselMmsi} onClose={() => setSelectedVesselMmsi(null)} />
      )}

      {selectedEvent && (
        <div className="event-detail-overlay" onClick={() => setSelectedEvent(null)}>
          <div className="event-detail-card" onClick={e => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setSelectedEvent(null)}>✕</button>
            <div className="event-detail-header">
              <span className="event-detail-icon">{eventTypeIcon(selectedEvent.event_type)}</span>
              <h3>{formatEventType(selectedEvent.event_type)}</h3>
            </div>
            <dl>
              <dt>Time</dt>
              <dd>{new Date(selectedEvent.event_time).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</dd>
              {buildEventRows(selectedEvent).map(([label, val]) => (
                <Fragment key={label}>
                  <dt>{label}</dt><dd>{val}</dd>
                </Fragment>
              ))}
              {selectedEvent.confidence != null && (
                <Fragment key="confidence">
                  <dt>Confidence</dt><dd>{Math.round(selectedEvent.confidence * 100)}%</dd>
                </Fragment>
              )}
              <dt>Collection</dt><dd>{selectedEvent.source}</dd>
              {selectedEvent.quality_flags.length > 0 && (
                <Fragment key="flags">
                  <dt>Alerts</dt><dd className="event-detail-flags">{selectedEvent.quality_flags.join(" · ")}</dd>
                </Fragment>
              )}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider><AppShell /></AuthProvider>
    </QueryClientProvider>
  );
}
