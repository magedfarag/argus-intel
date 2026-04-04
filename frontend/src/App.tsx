import { useState, useMemo, useEffect } from "react";
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
import { useImagerySearch } from "./hooks/useImagery";
import { useEventSearch } from "./hooks/useEvents";
import { useTracks } from "./hooks/useTracks";
import { useAois } from "./hooks/useAois";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { subDays } from "date-fns";
import type { CanonicalEvent } from "./api/types";
import "./App.css";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

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
  const [viewMode, setViewMode] = useLocalStorage<"2d" | "3d">("viewMode", "2d");
  const [layers, setLayers] = useLocalStorage("layers", {
    showAois: true, showImagery: true, showEvents: true,
    showGdelt: true, showShips: true, showAircraft: true,
    trackDensity: 1.0,
    // P2-3.3: imagery footprint opacity
    imageryOpacity: 0.1,
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

  // currentTime for TripsLayer — end of selected window (static replay)
  const tracksCurrentTime = Date.parse(endTime) / 1000;
  // trailLength covers the entire selected time range so all tracks are visible
  const tracksTrailLength = Math.max(300, (Date.parse(endTime) - Date.parse(startTime)) / 1000);

  const PANELS = [
    { key: "aoi", label: "AOIs" }, { key: "layers", label: "Layers" },
    { key: "search", label: "Events" }, { key: "playback", label: "Playback" },
    { key: "analytics", label: "Analytics" }, { key: "export", label: "Export" },
    { key: "compare", label: "Compare" }, { key: "health", label: "Health" },
  ];

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-title">
          <span className="app-icon">🗺</span>
          <h1>GEOINT Platform</h1>
          <span className="app-subtitle">Construction Activity Monitor</span>
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
            >{p.label}</button>
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
            />
          )}
          {activePanel === "analytics" && <AnalyticsPanel aoiId={selectedAoiId} startTime={startTime} endTime={endTime} />}
          {activePanel === "export" && (
            <ExportPanel aoiId={selectedAoiId} startTime={startTime} endTime={endTime} />
          )}
          {/* P2-3.2: before/after imagery compare panel */}
          {activePanel === "compare" && (
            <ImageryComparePanel items={imagerySearch.data ?? []} />
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
            />
          ) : (
            /* P2-5.1/5.2: globe.gl 3D overview */
            <GlobeView
              aois={aois}
              events={gdeltSearch.data ?? []}
              gdeltEvents={gdeltSearch.data ?? []}
              trips={visibleTracks}
              showEventLayer={layers.showEvents}
              showGdeltLayer={layers.showGdelt}
              showShipsLayer={layers.showShips}
              showAircraftLayer={layers.showAircraft}
            />
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