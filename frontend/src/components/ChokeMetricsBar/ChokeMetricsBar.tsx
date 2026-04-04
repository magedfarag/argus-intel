import { useQuery } from "@tanstack/react-query";
import { chokepointsApi } from "../../api/client";

const TREND_ICON: Record<string, string> = { "+": "▲", "-": "▼", "=": "━" };
const TREND_CLS: Record<string, string>  = { "+": "trend--up", "-": "trend--down", "=": "trend--flat" };
const THREAT_BG: Record<string, string>  = {
  CRITICAL: "#dc2626", HIGH: "#f97316", ELEVATED: "#ca8a04", LOW: "#15803d",
};

export function ChokeMetricsBar() {
  const { data } = useQuery({
    queryKey: ["chokepoints"],
    queryFn: () => chokepointsApi.list(),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const cps = data?.chokepoints ?? [];
  if (!cps.length) return null;

  return (
    <div className="choke-metrics-bar" data-testid="choke-metrics-bar">
      {cps.map(cp => (
        <div
          key={cp.id}
          className="choke-metric-cell"
          title={cp.description}
          style={{ borderTop: `2px solid ${THREAT_BG[cp.threat_label] ?? "#64748b"}` }}
        >
          <span className="choke-metric-name">{cp.name.replace("Strait of ", "")}</span>
          <span className="choke-metric-flow">
            {cp.daily_flow_mbbl}M bbl/d
            <span className={`choke-trend ${TREND_CLS[cp.trend] ?? ""}`}>
              {TREND_ICON[cp.trend] ?? "━"}
            </span>
          </span>
          <span
            className="choke-threat-pill"
            style={{ background: THREAT_BG[cp.threat_label] ?? "#64748b" }}
          >
            {cp.threat_label}
          </span>
        </div>
      ))}
    </div>
  );
}
