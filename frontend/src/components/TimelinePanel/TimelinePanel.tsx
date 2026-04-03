import { useState } from "react";
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
}

const PRESETS = [
  { label: "24h", getRange: () => ({ start: new Date(Date.now() - 86400_000), end: new Date() }) },
  { label: "7d",  getRange: () => ({ start: subDays(new Date(), 7), end: new Date() }) },
  { label: "30d", getRange: () => ({ start: subDays(new Date(), 30), end: new Date() }) },
];

const SOURCE_COLORS: Record<string, string> = {
  sentinel2: "#4caf50", landsat: "#8bc34a", gdelt: "#9c27b0",
  aisstream: "#00bcd4", opensky: "#ff5722",
};

export function TimelinePanel({ aoiId, startTime, endTime, onRangeChange }: Props) {
  const { data: buckets = [], isLoading } = useTimeline(startTime, endTime, aoiId ?? undefined);
  const [expanded, setExpanded] = useState(true);

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
  const sources = [...new Set(buckets.map(b => b.source))];

  return (
    <div className={`panel timeline-panel ${expanded ? "" : "timeline-panel--collapsed"}`} data-testid="timeline-panel">
      <div className="panel-header">
        <h3 className="panel-title">Timeline</h3>
        <button className="btn btn-xs" onClick={() => setExpanded(v => !v)}>{expanded ? "▼" : "▲"}</button>
      </div>
      {expanded && (
        <>
          <div className="preset-buttons">
            {PRESETS.map(p => (
              <button key={p.label} className="btn btn-sm" onClick={() => applyPreset(p)}>{p.label}</button>
            ))}
          </div>
          <div className="date-range">
            <input type="datetime-local" value={startTime.slice(0, 16)} onChange={e => onRangeChange(new Date(e.target.value).toISOString(), endTime)} className="input-sm" />
            <span>–</span>
            <input type="datetime-local" value={endTime.slice(0, 16)} onChange={e => onRangeChange(startTime, new Date(e.target.value).toISOString())} className="input-sm" />
          </div>
          {isLoading ? <p className="muted">Loading…</p> : rows.length > 0 ? (
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <XAxis dataKey="time" tickFormatter={t => format(new Date(t), "MM/dd")} tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} width={28} />
                <Tooltip labelFormatter={t => format(new Date(t), "PPp")} />
                {sources.map(s => (
                  <Bar key={s} dataKey={s} stackId="a" fill={SOURCE_COLORS[s] ?? "#64748b"} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="muted">No events in range</p>
          )}
        </>
      )}
    </div>
  );
}