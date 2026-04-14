import { DemoBadge } from '../DemoBadge';

interface LayerState {
  showAois: boolean;
  showImagery: boolean;
  showEvents: boolean;
  showGdelt: boolean;
  showShips: boolean;
  showAircraft: boolean;
  /** P3-3.6: fraction of tracks to render (1.0 = all, 0.1 = 10%). */
  trackDensity: number;
  /** P2-3.3: imagery footprint fill opacity (0–1). */
  imageryOpacity: number;
  showOrbits: boolean;
  showAirspace: boolean;
  showJamming: boolean;
  showStrikes: boolean;
  showTerrain: boolean;
  show3dBuildings: boolean;
  showDetections: boolean;
  showSignals: boolean;
}

interface Props {
  layers: LayerState;
  onChange: (layers: LayerState) => void;
  /** Optional demo-data flags for operational layers — drives DemoBadge rendering. */
  demoFlags?: {
    orbits?: boolean;
    airspace?: boolean;
    jamming?: boolean;
    strikes?: boolean;
  };
}

const LAYERS: { key: keyof LayerState; label: string; color: string; demoFlagKey?: keyof NonNullable<Props['demoFlags']> }[] = [
  { key: "showAois",    label: "AOI Boundaries",    color: "#2196f3" },
  { key: "showImagery", label: "Imagery Footprints", color: "#4caf50" },
  { key: "showEvents",  label: "Events",             color: "#f59e0b" },
  { key: "showGdelt",   label: "GDELT Context",      color: "#9c27b0" },
  { key: "showShips",   label: "Maritime (AIS)",     color: "#14ba8c" },
  { key: "showAircraft",label: "Aviation (ADS-B)",   color: "#ff5722" },
  { key: "showOrbits",        label: "Satellite Orbits",   color: "#00ff88", demoFlagKey: "orbits"   },
  { key: "showAirspace",      label: "Airspace NFZ/TFR",   color: "#ff4444", demoFlagKey: "airspace" },
  { key: "showJamming",       label: "GPS Jamming",        color: "#ff3232", demoFlagKey: "jamming"  },
  { key: "showStrikes",       label: "Strike Events",      color: "#ff2200", demoFlagKey: "strikes"  },
  { key: "showTerrain",       label: "Terrain (DEM)",      color: "#8b7355" },
  { key: "show3dBuildings",   label: "3D Buildings",       color: "#b0c4de" },
  { key: "showDetections",    label: "Detections (AI)",    color: "#ffdd00" },
  { key: "showSignals",       label: "Intel Signals",       color: "#22d3ee" },
];

export function LayerPanel({ layers, onChange, demoFlags }: Props) {
  const showTrackControls = layers.showShips || layers.showAircraft;
  return (
    <div className="panel" data-testid="layer-panel">
      <h3 className="panel-title">Layers</h3>
      {LAYERS.map(({ key, label, color, demoFlagKey }) => (
        <label key={key} className="layer-toggle">
          <input
            type="checkbox"
            checked={!!layers[key]}
            onChange={e => onChange({ ...layers, [key]: e.target.checked })}
          />
          <span className="layer-dot" style={{ background: color }} />
          {label}
          {demoFlagKey && <DemoBadge isDemo={demoFlags?.[demoFlagKey] ?? false} />}
        </label>
      ))}
      {/* P3-3.6: Track density control — shown when ships or aircraft layer is on */}
      {showTrackControls && (
        <div className="density-control" data-testid="density-control">
          <label className="density-label">
            Track density: {Math.round(layers.trackDensity * 100)}%
          </label>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.1}
            value={layers.trackDensity}
            onChange={e => onChange({ ...layers, trackDensity: parseFloat(e.target.value) })}
            className="density-slider"
            data-testid="density-slider"
          />
        </div>
      )}
      {/* P2-3.3: Imagery footprint opacity — shown when imagery layer is on */}
      {layers.showImagery && (
        <div className="density-control" data-testid="imagery-opacity-control">
          <label className="density-label">
            Imagery opacity: {Math.round(layers.imageryOpacity * 100)}%
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={layers.imageryOpacity}
            onChange={e => onChange({ ...layers, imageryOpacity: parseFloat(e.target.value) })}
            className="density-slider"
            data-testid="imagery-opacity-slider"
          />
        </div>
      )}
    </div>
  );
}