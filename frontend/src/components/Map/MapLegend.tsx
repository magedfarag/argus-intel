interface LegendItem {
  key: string;
  label: string;
  color: string;
  shape: "arrow" | "circle" | "dashed" | "fill";
}

const LEGEND_ITEMS: LegendItem[] = [
  { key: "ships",    label: "Ships",        color: "#00e5ff", shape: "arrow"  },
  { key: "aircraft", label: "Aircraft",     color: "#ff5722", shape: "arrow"  },
  { key: "events",   label: "Intel Events", color: "#f59e0b", shape: "circle" },
  { key: "gdelt",    label: "GDELT Events", color: "#c084fc", shape: "circle" },
  { key: "imagery",  label: "Imagery",      color: "#4caf50", shape: "dashed" },
  { key: "aois",     label: "AOI Zones",    color: "#3b82f6", shape: "fill"   },
  { key: "orbits",   label: "Orbit Passes",    color: "#00ff88", shape: "dashed"  },
  { key: "airspace", label: "Airspace TFR/NFZ", color: "#ff4444", shape: "fill"   },
  { key: "jamming",  label: "GPS Jamming",      color: "#ff3232", shape: "circle" },
  { key: "strikes",    label: "Strike Events",    color: "#ff2200", shape: "circle" },
  { key: "detections", label: "Detections (AI)",  color: "#ffdd00", shape: "circle" },
];

interface Props {
  showShips?: boolean;
  showAircraft?: boolean;
  showEvents?: boolean;
  showGdelt?: boolean;
  showImagery?: boolean;
  showOrbits?: boolean;
  showAirspace?: boolean;
  showJamming?: boolean;
  showStrikes?: boolean;
  showDetections?: boolean;
}

export function MapLegend({ showShips, showAircraft, showEvents, showGdelt, showImagery, showOrbits, showAirspace, showJamming, showStrikes, showDetections }: Props) {
  const visible = LEGEND_ITEMS.filter(({ key }) => {
    if (key === "ships")    return showShips;
    if (key === "aircraft") return showAircraft;
    if (key === "events")   return showEvents;
    if (key === "gdelt")    return showGdelt;
    if (key === "imagery")  return showImagery;
    if (key === "orbits")   return showOrbits;
    if (key === "airspace") return showAirspace;
    if (key === "jamming")  return showJamming;
    if (key === "strikes")     return showStrikes;
    if (key === "detections")  return showDetections;
    return true; // aois always shown
  });
  if (!visible.length) return null;
  return (
    <div className="map-legend">
      <div className="map-legend-title">LEGEND</div>
      {visible.map(item => (
        <div key={item.key} className="map-legend-row">
          <LegendBadge color={item.color} shape={item.shape} />
          <span className="map-legend-label">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function LegendBadge({ color, shape }: { color: string; shape: LegendItem["shape"] }) {
  if (shape === "arrow") {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <polygon points="7,1 13,13 7,10 1,13" fill={color} stroke="rgba(255,255,255,0.5)" strokeWidth="0.8" />
      </svg>
    );
  }
  if (shape === "circle") {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <circle cx="6" cy="6" r="5" fill={color} stroke="rgba(255,255,255,0.5)" strokeWidth="0.8" />
      </svg>
    );
  }
  if (shape === "dashed") {
    return (
      <svg width="18" height="8" viewBox="0 0 18 8" aria-hidden="true">
        <line x1="1" y1="4" x2="17" y2="4" stroke={color} strokeWidth="2" strokeDasharray="4 3" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg width="14" height="10" viewBox="0 0 14 10" aria-hidden="true">
      <rect x="1" y="1" width="12" height="8" rx="1" fill={color + "44"} stroke={color} strokeWidth="1.2" />
    </svg>
  );
}
