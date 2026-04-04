import { useState, useMemo, useEffect, useRef } from "react";
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

  // Track animation: null = live end-of-range, number = Unix seconds sim time
  const [playbackTime, setPlaybackTime] = useState<number | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const animRafRef = useRef<number | null>(null);
  const ANIM_SPEED_RATIO = 3600; // 1 real second = 1 simulated hour

  // Smooth rAF animation loop — advances simulation time from startTime to endTime
  useEffect(() => {
    if (!isAnimating) {
      if (animRafRef.current !== null) { cancelAnimationFrame(animRafRef.current); animRafRef.current = null; }
      return;
    }
    const simEnd   = Date.parse(endTime) / 1000;
    const simStart = playbackTime ?? (Date.parse(startTime) / 1000);
    const realStart = performance.now();
    function tick(now: number) {
      const elapsed = (now - realStart) / 1000;
      const next = simStart + elapsed * ANIM_SPEED_RATIO;
      if (next >= simEnd) { setPlaybackTime(simEnd); setIsAnimating(false); return; }
      setPlaybackTime(next);
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
  });

  // P2-5.2: fetch all AOIs to render on globe
  const aoiQuery = useAois();
  const aois = aoiQuery.data ?? [];

  // Auto-select first AOI when available and nothing is selected
  useEffect(() => {
    if (!selectedAoiId && aois.length > 0) {
      setSelectedAoiId(aois[0].id);
    }
  }, [aois, selectedAoiId]);

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

  const passesQuery = useAllSatellitePasses(orbitsQuery.orbits ?? [], aoiCenter.lon, aoiCenter.lat, 24);

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

  // currentTime for TripsLayer — driven by animation or playback, fallback to end of window
  const tracksCurrentTime = playbackTime ?? (Date.parse(endTime) / 1000);
  // trailLength covers the entire selected time range so all tracks are visible
  const tracksTrailLength = Math.max(300, (Date.parse(endTime) - Date.parse(startTime)) / 1000);

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
            <ImageryComparePanel items={imagerySearch.data ?? []} />
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
              imageryItems={imagerySearch.data ?? []}
              events={gdeltSearch.data ?? []}
              drawMode={drawMode}
              selectedAoiId={selectedAoiId}
              onAoiClick={setSelectedAoiId}
              onAoiDraw={geom => { setPendingGeometry(geom); setDrawMode("none"); }}
              onEventClick={setSelectedEvent}
              showImageryLayer={layers.showImagery}
              showEventLayer={layers.showEvents}
              gdeltEvents={gdeltSearch.data ?? []}
              showGdeltLayer={layers.showGdelt}
              imageryOpacity={layers.imageryOpacity}
              trips={visibleTracks}
              currentTime={tracksCurrentTime}
              trailLength={tracksTrailLength}
              showShipsLayer={layers.showShips}
              showAircraftLayer={layers.showAircraft}
              baseStyle={mapSettings.baseStyle}
              showOrbitsLayer={layers.showOrbits}
              orbitPasses={passesQuery.passes ?? []}
              showAirspaceLayer={layers.showAirspace}
              airspaceRestrictions={filteredAirspaceRestrictions(airspaceQuery.restrictions ?? [])}
              showJammingLayer={layers.showJamming}
              jammingEvents={filteredJammingEvents(jammingQuery.events ?? [])}
              showStrikesLayer={layers.showStrikes}
              strikeEvents={filteredStrikes(strikesQuery.strikes ?? [])}
              showDetectionsLayer={layers.showDetections}
              detections={detectionsQuery.detections ?? []}
              renderMode={renderMode}
              onStrikeClick={(id) => setSelectedEntityId(id)}
              centerPoint={cameraFocusPoint ?? undefined}
            />
          ) : (
            /* P2-5.1/5.2: globe.gl 3D overview */
            <>
              <GlobeView
                aois={aois}
                events={gdeltSearch.data ?? []}
                gdeltEvents={gdeltSearch.data ?? []}
                trips={visibleTracks}
                showEventLayer={layers.showEvents}
                showGdeltLayer={layers.showGdelt}
                showShipsLayer={layers.showShips}
                showAircraftLayer={layers.showAircraft}
                currentTime={tracksCurrentTime}
                trailLength={tracksTrailLength}
                showOrbitsLayer={layers.showOrbits}
                orbitPasses={passesQuery.passes ?? []}
                showAirspaceLayer={layers.showAirspace}
                airspaceRestrictions={filteredAirspaceRestrictions(airspaceQuery.restrictions ?? [])}
                showJammingLayer={layers.showJamming}
                jammingEvents={filteredJammingEvents(jammingQuery.events ?? [])}
                showStrikesLayer={layers.showStrikes}
                strikeEvents={filteredStrikes(strikesQuery.strikes ?? [])}
                showTerrainLayer={layers.showTerrain}
                show3dBuildingsLayer={layers.show3dBuildings}
                showDetectionsLayer={layers.showDetections}
                detections={detectionsQuery.detections ?? []}
                renderMode={renderMode}
                selectedEntityId={selectedEntityId}
                centerPoint={cameraFocusPoint ?? undefined}
              />
              {/* P6: Intel briefing overlay (top-right of globe) */}
              <div className="globe-intel-overlay">
                <IntelBriefingPanel compact={true} />
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
            <h3>{selectedEvent.event_type.replace(/_/g, " ")}</h3>
            <dl>
              <dt>Source</dt><dd>{selectedEvent.source}</dd>
              <dt>Time</dt><dd>{new Date(selectedEvent.event_time).toLocaleString()}</dd>
              {selectedEvent.confidence != null && <><dt>Confidence</dt><dd>{Math.round(selectedEvent.confidence * 100)}%</dd></>}
              {selectedEvent.quality_flags.length > 0 && <><dt>Flags</dt><dd>{selectedEvent.quality_flags.join(", ")}</dd></>}
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