import { useState, useMemo } from 'react';
import { useCameras, useCameraObservations } from '../../hooks/useCameras';
import type { CameraInfo, CameraObservation, MediaClipRef } from '../../types/sensorFusion';

const CAMERA_TYPE_LABEL: Record<string, string> = {
  optical: 'OPT',
  thermal: 'THM',
  night_vision: 'NV',
  radar: 'RDR',
  sar: 'SAR',
};

interface Props {
  onJumpToLocation?: (lon: number, lat: number) => void;
  currentTime?: number;  // Unix seconds
}

function CameraListItem({
  camera,
  selected,
  onSelect,
}: {
  camera: CameraInfo;
  selected: boolean;
  onSelect: () => void;
}) {
  const typeLabel = CAMERA_TYPE_LABEL[camera.camera_type] ?? camera.camera_type.toUpperCase();
  const isFixed = !camera.geo_registration.is_mobile;

  return (
    <li
      className={`cam-list-item${selected ? ' cam-list-item--active' : ''}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect()}
    >
      <span className="cam-list-arrow">{selected ? '▼' : '▶'}</span>
      <span className="cam-list-id">{camera.camera_id}</span>
      <span className="cam-type-badge">{typeLabel}</span>
      {isFixed && <span className="cam-live-badge">●LIVE</span>}
    </li>
  );
}

function ObservationRow({ obs, isNearest }: { obs: CameraObservation; isNearest?: boolean }) {
  const dt = new Date(obs.observed_at);
  const label = dt.toISOString().slice(0, 16).replace('T', ' ') + 'Z';

  return (
    <div className={`cam-obs-row${isNearest ? ' cam-obs-row--nearest' : ''}`}>
      {obs.thumbnail_url ? (
        <img className="cam-thumb" src={obs.thumbnail_url} alt="observation thumbnail" />
      ) : (
        <div className="cam-thumb cam-thumb--placeholder" aria-label="no thumbnail">
          <span>🎞</span>
        </div>
      )}
      <div className="cam-obs-meta">
        <span className="cam-obs-time">{label}</span>
        <span className="cam-obs-conf">conf: {Math.round(obs.confidence * 100)}%</span>
        {obs.tags.length > 0 && (
          <span className="cam-obs-tags">{obs.tags.join(' · ')}</span>
        )}
      </div>
    </div>
  );
}

function ClipPlayer({ clip, cameraId, isNearest, onJump }: { clip: MediaClipRef; cameraId: string; isNearest?: boolean; onJump?: () => void }) {
  const [playing, setPlaying] = useState(false);

  return (
    <div className={`cam-clip-card${isNearest ? ' cam-clip-card--nearest' : ''}`}>
      <div className="cam-clip-header">
        <span className="cam-clip-id">{clip.clip_id}</span>
        <span className="cam-clip-meta">
          {clip.duration_sec}s{clip.is_loopable ? ' · loopable' : ''}
          {clip.resolution_width ? ` · ${clip.resolution_width}×${clip.resolution_height}` : ''}
        </span>
      </div>
      {playing ? (
        <div className="cam-clip-demo" aria-label={`Demo clip ${clip.clip_id}`}>
          <span className="cam-clip-demo-label">
            DEMO CLIP — {clip.clip_id} ({clip.duration_sec}s)
          </span>
          <button
            className="btn btn-xs"
            onClick={() => setPlaying(false)}
            title="Stop"
          >
            ⏹ Stop
          </button>
        </div>
      ) : (
        <button
          className="btn btn-xs cam-clip-play-btn"
          onClick={() => setPlaying(true)}
          title={`Play ${clip.clip_id}`}
        >
          ▶ PLAY
        </button>
      )}
      {onJump && (
        <button
          className="btn btn-xs cam-jump-btn"
          onClick={onJump}
          title="Jump to camera location on map"
        >
          📍 Jump to map location
        </button>
      )}
    </div>
  );
}

function CameraDetail({
  camera,
  onJumpToLocation,
  currentTime,
}: {
  camera: CameraInfo;
  onJumpToLocation?: (lon: number, lat: number) => void;
  currentTime?: number;
}) {
  const { observations, clips, loading } = useCameraObservations(camera.camera_id);
  const geo = camera.geo_registration;

  const nearestObservationId = useMemo(() => {
    if (currentTime == null || observations.length === 0) return null;
    const nearest = observations.reduce((best, obs) => {
      const t = new Date(obs.observed_at).getTime() / 1000;
      const bestT = new Date(best.observed_at).getTime() / 1000;
      return Math.abs(t - currentTime) < Math.abs(bestT - currentTime) ? obs : best;
    }, observations[0]);
    return nearest.observation_id;
  }, [observations, currentTime]);

  const nearestClipRef = useMemo(() => {
    if (!nearestObservationId) return null;
    const nearestObs = observations.find(o => o.observation_id === nearestObservationId);
    return nearestObs?.clip_ref ?? null;
  }, [observations, nearestObservationId]);

  return (
    <div className="cam-detail">
      <div className="cam-detail-header">
        <span className="cam-detail-id">{camera.camera_id}</span>
        <span className="cam-type-badge">{camera.camera_type}</span>
      </div>
      <div className="cam-detail-geo">
        <span>
          {geo.lon.toFixed(2)}°E, {geo.lat.toFixed(2)}°N
        </span>
        <span className="cam-detail-sep">|</span>
        <span>Heading: {geo.heading_deg}°</span>
        <span className="cam-detail-sep">|</span>
        <span>FOV: {geo.fov_horizontal_deg}°×{geo.fov_vertical_deg}°</span>
        {geo.altitude_m !== undefined && (
          <>
            <span className="cam-detail-sep">|</span>
            <span>Alt: {geo.altitude_m}m</span>
          </>
        )}
      </div>
      <div className="cam-detail-source muted-small">Source: {camera.source}</div>

      <div className="cam-section-title">── Recent Observations ──</div>
      {loading && <p className="muted">Loading…</p>}
      {!loading && observations.length === 0 && (
        <p className="muted">No observations found</p>
      )}
      {observations.map(obs => (
        <ObservationRow
          key={obs.observation_id}
          obs={obs}
          isNearest={obs.observation_id === nearestObservationId}
        />
      ))}

      {clips.length > 0 && (
        <>
          <div className="cam-section-title">── Demo Clips ──</div>
          {clips.map(clip => (
            <ClipPlayer
              key={clip.clip_id}
              clip={clip}
              cameraId={camera.camera_id}
              isNearest={clip.clip_id === nearestClipRef}
              onJump={
                onJumpToLocation
                  ? () => onJumpToLocation(geo.lon, geo.lat)
                  : undefined
              }
            />
          ))}
        </>
      )}

      {!loading && clips.length === 0 && (
        <div className="cam-section-title">── Demo Clips ──</div>
      )}
      {!loading && clips.length === 0 && (
        <p className="muted">No clips available</p>
      )}
    </div>
  );
}

export function CameraFeedPanel({ onJumpToLocation, currentTime }: Props) {
  const { cameras, loading, error } = useCameras();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectedCamera: CameraInfo | undefined = cameras.find(c => c.camera_id === selectedId);

  if (loading) {
    return (
      <div className="panel" data-testid="camera-feed-panel">
        <p className="muted">Loading cameras…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel" data-testid="camera-feed-panel">
        <p className="error">Camera feeds unavailable</p>
      </div>
    );
  }

  return (
    <div className="panel" data-testid="camera-feed-panel">
      <div className="panel-header">
        <h3 className="panel-title">Camera Feeds</h3>
        <span className="count-badge">{cameras.length}</span>
      </div>

      <div className="cam-layout">
        {/* Left: camera list */}
        <ul className="cam-list">
          {cameras.length === 0 && (
            <li className="muted">No cameras registered</li>
          )}
          {cameras.map(cam => (
            <CameraListItem
              key={cam.camera_id}
              camera={cam}
              selected={cam.camera_id === selectedId}
              onSelect={() =>
                setSelectedId(prev => (prev === cam.camera_id ? null : cam.camera_id))
              }
            />
          ))}
        </ul>

        {/* Right: camera detail */}
        {selectedCamera && (
          <CameraDetail
            camera={selectedCamera}
            onJumpToLocation={onJumpToLocation}
            currentTime={currentTime}
          />
        )}
        {!selectedCamera && cameras.length > 0 && (
          <p className="muted cam-select-hint">Select a camera to inspect</p>
        )}
      </div>
    </div>
  );
}
