import { useState, useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { MapView } from "./components/Map/MapView";
import { AoiPanel } from "./components/AoiPanel/AoiPanel";
import { LayerPanel } from "./components/LayerPanel/LayerPanel";
import { TimelinePanel } from "./components/TimelinePanel/TimelinePanel";
import { SearchPanel } from "./components/SearchPanel/SearchPanel";
import { PlaybackPanel } from "./components/PlaybackPanel/PlaybackPanel";
import { AnalyticsPanel } from "./components/AnalyticsPanel/AnalyticsPanel";
import { ExportPanel } from "./components/ExportPanel/ExportPanel";
import { useImagerySearch } from "./hooks/useImagery";
import { useEventSearch } from "./hooks/useEvents";
import { useTracks } from "./hooks/useTracks";
import { subDays } from "date-fns";
import type { CanonicalEvent } from "./api/types";
import "./App.css";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

function AppShell() {
  const { apiKey, setApiKey } = useAuth();
  const [selectedAoiId, setSelectedAoiId] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState<"none" | "polygon" | "bbox">("none");
  const [pendingGeometry, setPendingGeometry] = useState<GeoJSON.Geometry | null>(null);
  const [startTime, setStartTime] = useState<string>(subDays(new Date(), 30).toISOString());
  const [endTime, setEndTime] = useState<string>(new Date().toISOString());
  const [selectedEvent, setSelectedEvent] = useState<CanonicalEvent | null>(null);
  const [activePanel, setActivePanel] = useState<string>("aoi");
  const [layers, setLayers] = useState({
    showAois: true, showImagery: true, showEvents: true,
    showGdelt: false, showShips: false, showAircraft: false,
    trackDensity: 1.0,
  });

  const imagerySearch = useImagerySearch(selectedAoiId ? {
    aoi_id: selectedAoiId,
    start_date: startTime.slice(0, 10),
    end_date: endTime.slice(0, 10),
    max_cloud_cover: 30,
  } : null);

  // P2-1.5/1.6: Fetch GDELT contextual events when layer is enabled
  const gdeltSearch = useEventSearch(
    layers.showGdelt && selectedAoiId
      ? { aoi_id: selectedAoiId, start_time: startTime, end_time: endTime, source_types: ["context"], limit: 300 }
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

  const PANELS = [
    { key: "aoi", label: "AOIs" }, { key: "layers", label: "Layers" },
    { key: "search", label: "Events" }, { key: "playback", label: "Playback" },
    { key: "analytics", label: "Analytics" }, { key: "export", label: "Export" },
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
          {activePanel === "analytics" && <AnalyticsPanel aoiId={selectedAoiId} />}
          {activePanel === "export" && (
            <ExportPanel aoiId={selectedAoiId} startTime={startTime} endTime={endTime} />
          )}
        </div>
        <div className="map-area">
          <MapView
            aois={[]}
            imageryItems={imagerySearch.data ?? []}
            events={[]}
            drawMode={drawMode}
            selectedAoiId={selectedAoiId}
            onAoiClick={setSelectedAoiId}
            onAoiDraw={geom => { setPendingGeometry(geom); setDrawMode("none"); }}
            onEventClick={setSelectedEvent}
            showImageryLayer={layers.showImagery}
            showEventLayer={layers.showEvents}
            gdeltEvents={gdeltSearch.data ?? []}
            showGdeltLayer={layers.showGdelt}
            trips={visibleTracks}
            currentTime={tracksCurrentTime}
            showShipsLayer={layers.showShips}
            showAircraftLayer={layers.showAircraft}
          />
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