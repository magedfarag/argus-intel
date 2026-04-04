import { useQuery } from "@tanstack/react-query";
import { darkShipsApi } from "../../api/client";
import type { DarkShipCandidate } from "../../api/types";
import { format } from "date-fns";

const RISK_COLOR: Record<string, string> = {
  critical: "#dc2626", high: "#f97316", medium: "#eab308", low: "#22c55e", unknown: "#64748b",
};

interface Props {
  onCandidateSelect?: (c: DarkShipCandidate) => void;
}

export function DarkShipPanel({ onCandidateSelect }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dark-ships"],
    queryFn: () => darkShipsApi.list(),
    staleTime: 120_000,
  });

  if (isLoading) return <div className="panel"><p className="muted">Running detection…</p></div>;
  if (error) return <div className="panel"><p className="error">Detection unavailable</p></div>;

  const candidates = data?.candidates ?? [];

  return (
    <div className="panel" data-testid="dark-ship-panel">
      <div className="panel-header">
        <h3 className="panel-title">Dark Ships</h3>
        <span className="count-badge">{candidates.length}</span>
      </div>
      {candidates.length === 0 && <p className="muted">No dark ship events detected</p>}
      <ul className="dark-ship-list">
        {candidates.map(c => (
          <li
            key={c.event_id}
            className="dark-ship-item"
            onClick={() => onCandidateSelect?.(c)}
          >
            <div className="ds-header">
              <span className="ds-vessel">{c.vessel_name}</span>
              {c.sanctions_flag && <span className="sanctions-badge">⚠ SANCTIONED</span>}
              <span
                className="risk-dot"
                style={{ background: RISK_COLOR[c.dark_ship_risk] ?? "#64748b" }}
                title={`Risk: ${c.dark_ship_risk}`}
              />
            </div>
            <div className="ds-gap-bar" title={`${c.gap_hours}h dark`}>
              <div
                className="ds-gap-fill"
                style={{ width: `${Math.min(100, (c.gap_hours / 72) * 100)}%`, background: RISK_COLOR[c.dark_ship_risk] ?? "#64748b" }}
              />
            </div>
            <div className="ds-meta">
              <span className="muted-small">
                {format(new Date(c.gap_start), "MMM d HH:mm")} → {format(new Date(c.gap_end), "MMM d HH:mm")}
              </span>
              <span className="ds-duration">{c.gap_hours}h dark</span>
              {c.position_jump_km != null && (
                <span className="ds-jump">{c.position_jump_km} km jump</span>
              )}
            </div>
            <div className="ds-confidence">
              Confidence: <strong>{Math.round(c.confidence * 100)}%</strong>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
