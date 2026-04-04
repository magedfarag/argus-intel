import { useQuery } from "@tanstack/react-query";
import { chokepointsApi } from "../../api/client";
import type { Chokepoint } from "../../api/types";

const THREAT_COLOR: Record<string, string> = {
  CRITICAL: "#dc2626", HIGH: "#f97316", ELEVATED: "#eab308", LOW: "#22c55e",
};

interface Props {
  onChokepointSelect?: (cp: Chokepoint) => void;
}

export function ChokepointPanel({ onChokepointSelect }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["chokepoints"],
    queryFn: () => chokepointsApi.list(),
    staleTime: 60_000,
  });

  if (isLoading) return <div className="panel"><p className="muted">Loading chokepoints…</p></div>;
  if (error) return <div className="panel"><p className="error">Failed to load chokepoints</p></div>;

  const cps = data?.chokepoints ?? [];

  return (
    <div className="panel" data-testid="chokepoint-panel">
      <h3 className="panel-title">Chokepoints</h3>
      <ul className="chokepoint-list">
        {cps.map(cp => (
          <li
            key={cp.id}
            className="chokepoint-item"
            onClick={() => onChokepointSelect?.(cp)}
            style={{ borderLeft: `3px solid ${THREAT_COLOR[cp.threat_label] ?? "#64748b"}` }}
          >
            <div className="chokepoint-header">
              <span className="chokepoint-name">{cp.name}</span>
              <span
                className="threat-badge"
                style={{ background: THREAT_COLOR[cp.threat_label] ?? "#64748b" }}
              >
                {cp.threat_label}
              </span>
            </div>
            <div className="chokepoint-meta">
              <span>{cp.daily_flow_mbbl} MBBL/day</span>
              <span className={`trend-indicator trend--${cp.trend === "+" ? "up" : cp.trend === "-" ? "down" : "flat"}`}>
                {cp.trend === "+" ? "▲" : cp.trend === "-" ? "▼" : "━"}
              </span>
              <span className="muted-small">{cp.vessel_count_24h} vessels / 24h</span>
            </div>
            <p className="chokepoint-desc">{cp.description.slice(0, 100)}…</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
