import { useState, useMemo } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useTimeline } from "../../hooks/useEvents";
import { format, subDays } from "date-fns";

interface TimelineRow {
  time: string;
  [source: string]: string | number;
}

interface Props {
  aoiId: string | null;
  startTime: string;
  endTime: string;
  onRangeChange: (start: string, end: string) => void;
  onTimeSeek?: (isoTime: string) => void;
}

const PRESETS = [
  { label: "24h", getRange: () => ({ start: new Date(Date.now() - 86400_000), end: new Date() }) },
  { label: "7d",  getRange: () => ({ start: subDays(new Date(), 7), end: new Date() }) },
  { label: "30d", getRange: () => ({ start: subDays(new Date(), 30), end: new Date() }) },
];

const SOURCE_COLORS: Record<string, string> = {
  sentinel2: "#4caf50", landsat: "#8bc34a", gdelt: "#9c27b0",
  aisstream: "#00bcd4", opensky: "#ff5722",
  // Signal connectors
  "usgs-earthquake": "#ef4444", "nasa-eonet": "#f97316",
  "open-meteo": "#3b82f6", acled: "#dc2626",
  "nga-msi": "#06b6d4", "osm-military": "#7c3aed",
  "nasa-firms": "#ea580c", "noaa-swpc": "#8b5cf6",
  openaq: "#22c55e",
  // Other imagery / telemetry connectors
  "cdse-sentinel2": "#4caf50", "usgs-landsat": "#8bc34a",
  "earth-search": "#66bb6a", "planetary-computer": "#81c784",
  "gdelt-doc": "#9c27b0", "ais-stream": "#00bcd4",
  "vessel-data": "#26c6da", "rapidapi-ais": "#00acc1",
};

interface DotBucket {
  time: string;
  count: number;
  source: string;
  pct: number;
}

interface TooltipState {
  x: number;
  y: number;
  bucket: DotBucket;
} 

const PANEL_STYLES: React.CSSProperties = {
  position: "fixed",
  bottom: 0,
  left: 0,
  right: 0,
  background: "rgba(14, 28, 48, 0.97)",
  borderTop: "2px solid rgba(0, 212, 255, 0.6)",
  zIndex: 1000,
  transition: "height 0.2s ease",
  overflow: "hidden",
};

export function TimelinePanel({ aoiId, startTime, endTime, onRangeChange, onTimeSeek }: Props) {
  const { data: buckets = [], isLoading } = useTimeline(startTime, endTime, aoiId ?? undefined);
  const [expanded, setExpanded] = useState(false);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  function applyPreset(preset: typeof PRESETS[0]) {
    const { start, end } = preset.getRange();
    onRangeChange(start.toISOString(), end.toISOString());
  }

  const chartData = buckets.reduce<Record<string, TimelineRow>>((acc, b) => {
    if (!acc[b.time]) acc[b.time] = { time: b.time };
    acc[b.time][b.source] = ((acc[b.time][b.source] as number) ?? 0) + b.count;
    return acc;
  }, {});
  const rows = Object.values(chartData);
  const sources = [...new Set(buckets.map(b => b.source))].filter(Boolean);

  const rangeStart = new Date(startTime).getTime();
  const rangeEnd = new Date(endTime).getTime();
  const rangeMs = rangeEnd - rangeStart || 1;

  const dots: DotBucket[] = useMemo(() => {
    return buckets.map(b => ({
      time: b.time,
      count: b.count,
      source: b.source,
      pct: Math.max(0, Math.min(100, (new Date(b.time).getTime() - rangeStart) / rangeMs * 100)),
    }));
  }, [buckets, rangeStart, rangeMs]);

  const panelHeight = expanded ? 120 : 40;

  return (
    <div
      className="timeline-panel"
      data-testid="timeline-panel"
      style={{ ...PANEL_STYLES, height: panelHeight }}
    >
      {/* Collapsed scrubber strip — always visible */}
      <div style={{ position: "relative", height: 40, display: "flex", alignItems: "center" }}>
        {/* Track line */}
        <div style={{
          position: "absolute",
          left: 48, right: 48,
          top: "50%",
          height: 2,
          background: "rgba(0, 212, 255, 0.55)",
          transform: "translateY(-50%)",
          borderRadius: 1,
        }} />

        {/* Event dots — SVG layer */}
        <svg
          style={{ position: "absolute", left: 48, right: 48, top: 0, bottom: 0, width: "calc(100% - 96px)", height: 40 }}
          preserveAspectRatio="none"
          viewBox="0 0 100 40"
        >
          {dots.map((d, i) => {
            const r = Math.max(3, Math.min(10, Math.sqrt(d.count) * 2));
            const color = SOURCE_COLORS[d.source] ?? "#64748b";
            return (
              <circle
                key={i}
                cx={d.pct}
                cy={20}
                r={r * 0.45}  /* scale r into 0-100 viewBox units (100px wide → ~0.45 factor) */
                fill={color}
                fillOpacity={0.85}
                style={{ cursor: "pointer", transition: "r 0.15s ease" }}
                onMouseEnter={e => {
                  const rect = (e.currentTarget.closest("svg") as SVGSVGElement).getBoundingClientRect();
                  setTooltip({
                    x: rect.left + (d.pct / 100) * rect.width,
                    y: rect.top,
                    bucket: d,
                  });
                }}
                onMouseLeave={() => setTooltip(null)}
                onClick={() => onTimeSeek?.(d.time)}
              />
            );
          })}
        </svg>

        {/* Label */}
        <span style={{ position: "absolute", left: 8, fontSize: 10, color: "rgba(0,212,255,0.95)", letterSpacing: "0.08em", userSelect: "none", fontWeight: 700, textShadow: "0 0 8px rgba(0,212,255,0.45)" }}>
          {isLoading ? "…" : "TIMELINE"}
        </span>

        {/* Expand toggle */}
        <button
          onClick={() => setExpanded(v => !v)}
          style={{
            position: "absolute", right: 8,
            background: "none", border: "none", cursor: "pointer",
            color: "rgba(0,212,255,1)", fontSize: 12, padding: "2px 6px",
            lineHeight: 1, fontWeight: 700,
          }}
          title={expanded ? "Collapse" : "Expand"}
        >
          {expanded ? "▼" : "▲"}
        </button>
      </div>

      {/* Expanded area — bar chart + controls */}
      {expanded && (
        <div style={{ padding: "0 8px 4px" }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
            {PRESETS.map(p => (
              <button
                key={p.label}
                className="btn btn-sm"
                onClick={() => applyPreset(p)}
                style={{ fontSize: 10, padding: "1px 6px" }}
              >
                {p.label}
              </button>
            ))}
            <input
              type="datetime-local"
              value={startTime.slice(0, 16)}
              onChange={e => onRangeChange(new Date(e.target.value).toISOString(), endTime)}
              className="input-sm"
              style={{ fontSize: 10, marginLeft: "auto" }}
            />
            <span style={{ color: "#94a3b8", alignSelf: "center" }}>–</span>
            <input
              type="datetime-local"
              value={endTime.slice(0, 16)}
              onChange={e => onRangeChange(startTime, new Date(e.target.value).toISOString())}
              className="input-sm"
              style={{ fontSize: 10 }}
            />
          </div>
          {rows.length > 0 ? (
            <ResponsiveContainer width="100%" height={60}>
              <BarChart data={rows} margin={{ top: 2, right: 8, left: 0, bottom: 2 }}>
                <XAxis dataKey="time" tickFormatter={t => format(new Date(t), "MM/dd")} tick={{ fontSize: 9 }} />
                <YAxis tick={{ fontSize: 9 }} width={24} />
                <Tooltip labelFormatter={t => format(new Date(t), "PPp")} />
                {sources.map(s => (
                  <Bar key={s} dataKey={s} stackId="a" fill={SOURCE_COLORS[s] ?? "#64748b"} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="muted" style={{ fontSize: 10, margin: "4px 0" }}>No events in range</p>
          )}
        </div>
      )}

      {/* Hover tooltip */}
      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x,
            top: tooltip.y - 56,
            transform: "translateX(-50%)",
            background: "rgba(10, 15, 20, 0.95)",
            border: "1px solid rgba(0,212,255,0.3)",
            borderRadius: 4,
            padding: "4px 8px",
            fontSize: 11,
            color: "#e2e8f0",
            pointerEvents: "none",
            zIndex: 1010,
            whiteSpace: "nowrap",
          }}
        >
          <div style={{ color: "rgba(0,212,255,0.9)", marginBottom: 2 }}>
            {format(new Date(tooltip.bucket.time), "MMM d, HH:mm")}
          </div>
          <div>
            <span style={{ color: SOURCE_COLORS[tooltip.bucket.source] ?? "#94a3b8" }}>{tooltip.bucket.source}</span>
            {" "}&nbsp;{tooltip.bucket.count} events
          </div>
        </div>
      )}
    </div>
  );
}