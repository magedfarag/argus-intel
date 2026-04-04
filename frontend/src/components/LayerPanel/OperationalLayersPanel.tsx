// OperationalLayersPanel — toggles for the 4 Phase 2 operational layers.
// Follows the same `.panel` / `.layer-toggle` patterns as LayerPanel.tsx.

interface Props {
  layerVisibility: Record<string, boolean>;
  onToggle: (layer: string, visible: boolean) => void;
}

const OPERATIONAL_LAYERS: { key: string; label: string; color: string }[] = [
  { key: 'orbits',      label: 'Orbit Tracks',          color: '#00e5ff' },
  { key: 'airspace',    label: 'Airspace Restrictions',  color: '#4caf50' },
  { key: 'jamming',     label: 'GPS Jamming Heatmap',    color: '#ffab00' },
  { key: 'strikes',     label: 'Strike Markers',         color: '#ff1744' },
];

export function OperationalLayersPanel({ layerVisibility, onToggle }: Props) {
  return (
    <div className="panel" data-testid="operational-layers-panel">
      <h3 className="panel-title">Operational Layers</h3>
      {OPERATIONAL_LAYERS.map(({ key, label, color }) => (
        <label key={key} className="layer-toggle">
          <input
            type="checkbox"
            checked={!!layerVisibility[key]}
            onChange={e => onToggle(key, e.target.checked)}
          />
          <span className="layer-dot" style={{ background: color }} />
          {label}
        </label>
      ))}
    </div>
  );
}
