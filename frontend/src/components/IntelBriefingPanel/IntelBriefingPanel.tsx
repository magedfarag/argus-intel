import { useQuery } from "@tanstack/react-query";
import { intelApi } from "../../api/client";

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "#dc2626", HIGH: "#f97316", MODERATE: "#eab308", LOW: "#22c55e",
};

interface Props {
  compact?: boolean;
  onVesselSelect?: (mmsi: string) => void;
}

export function IntelBriefingPanel({ compact = false, onVesselSelect }: Props) {
  const { data: briefing, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["intel-briefing"],
    queryFn: () => intelApi.briefing(),
    staleTime: 300_000,
    refetchInterval: 300_000,
  });

  if (isLoading) return (
    <div className="intel-briefing-panel panel">
      <p className="muted">Loading briefing...</p>
    </div>
  );
  if (error || !briefing) return null;

  const riskColor = RISK_COLORS[briefing.risk_level] ?? "#64748b";

  return (
    <div className={`intel-briefing-panel panel${compact ? " intel-briefing-panel--compact" : ""}`} data-testid="intel-briefing-panel">
      <div className="intel-classification">{briefing.classification}</div>
      <div className="intel-header">
        <span className="intel-title">INTELLIGENCE BRIEFING</span>
        <span className="intel-risk" style={{ color: riskColor }}>
          {briefing.risk_level}
        </span>
      </div>
      <p className="intel-summary">{briefing.executive_summary}</p>
      {!compact && (
        <>
          <div className="intel-stats">
            <div className="stat-pill"><span>{briefing.dark_ship_count}</span><label>Dark Ships</label></div>
            <div className="stat-pill"><span>{briefing.sanctioned_vessel_count}</span><label>Sanctioned</label></div>
            <div className="stat-pill"><span>{briefing.active_vessel_count}</span><label>Active</label></div>
          </div>
          <div className="intel-section">
            <h4 className="intel-section-title">Key Findings</h4>
            <ol className="intel-findings">
              {briefing.key_findings.map((f, i) => (
                <li key={i} className="intel-finding">{f}</li>
              ))}
            </ol>
          </div>
        </>
      )}
      {briefing.vessel_alerts.length > 0 && (
        <div className="intel-section">
          <h4 className="intel-section-title">Vessel Alerts</h4>
          <ul className="vessel-alert-list">
            {briefing.vessel_alerts.map(a => (
              <li
                key={a.mmsi}
                className={`vessel-alert vessel-alert--${a.alert_type}`}
                onClick={() => onVesselSelect?.(a.mmsi)}
                style={onVesselSelect ? { cursor: "pointer" } : undefined}
              >
                <div className="va-header">
                  <span className="va-name">{a.vessel_name}</span>
                  <span className="va-type">{a.alert_type.replace(/_/g, " ").toUpperCase()}</span>
                  <span className="va-conf">{Math.round(a.confidence * 100)}%</span>
                </div>
                {!compact && <p className="va-detail">{a.detail}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="intel-updated muted-small">
        Updated {dataUpdatedAt ? new Date(dataUpdatedAt).toISOString().slice(11, 16) : "---"} UTC
      </p>
    </div>
  );
}
