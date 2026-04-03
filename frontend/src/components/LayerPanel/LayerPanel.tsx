interface LayerState {
  showAois: boolean;
  showImagery: boolean;
  showEvents: boolean;
  showGdelt: boolean;
  showShips: boolean;
  showAircraft: boolean;
  /** P3-3.6: fraction of tracks to render (1.0 = all, 0.1 = 10%). */
  trackDensity: number;
}

interface Props {
  layers: LayerState;
  onChange: (layers: LayerState) => void;
}

const LAYERS: { key: keyof LayerState; label: string; color: string }[] = [
  { key: "showAois",    label: "AOI Boundaries",    color: "#2196f3" },
  { key: "showImagery", label: "Imagery Footprints", color: "#4caf50" },
  { key: "showEvents",  label: "Events",             color: "#f59e0b" },
  { key: "showGdelt",   label: "GDELT Context",      color: "#9c27b0" },
  { key: "showShips",   label: "Maritime (AIS)",     color: "#00bcd4" },
  { key: "showAircraft",label: "Aviation (ADS-B)",   color: "#ff5722" },
];

export function LayerPanel({ layers, onChange }: Props) {
  const showTrackControls = layers.showShips || layers.showAircraft;
  return (
    <div className="panel" data-testid="layer-panel">
      <h3 className="panel-title">Layers</h3>
      {LAYERS.map(({ key, label, color }) => (
        <label key={key} className="layer-toggle">
          <input
            type="checkbox"
            checked={!!layers[key]}
            onChange={e => onChange({ ...layers, [key]: e.target.checked })}
          />
          <span className="layer-dot" style={{ background: color }} />
          {label}
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
    </div>
  );
}