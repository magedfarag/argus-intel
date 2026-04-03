import { useEffect, useState } from "react";
import type { HealthDashboardResponse, SourceHealthRecord, HealthAlert } from "../../api/types";
import { healthApi } from "../../api/client";

interface Props {
  refreshIntervalMs?: number;
}

function FreshnessChip({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    fresh: "var(--color-accent-green, #22c55e)",
    stale: "var(--color-accent-yellow, #f59e0b)",
    critical: "var(--color-accent-red, #ef4444)",
    unknown: "var(--color-muted, #71717a)",
  };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.7rem",
        fontWeight: 600,
        background: colorMap[status] || colorMap.unknown,
        color: "#fff",
        textTransform: "capitalize",
      }}
    >
      {status}
    </span>
  );
}

function AlertBanner({ alerts }: { alerts: HealthAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <div
      style={{
        background: "var(--color-accent-red, #ef4444)",
        color: "#fff",
        borderRadius: 6,
        padding: "8px 12px",
        marginBottom: 12,
        fontSize: "0.85rem",
      }}
      data-testid="health-alerts-banner"
    >
      <strong>{alerts.length} active alert{alerts.length > 1 ? "s" : ""}</strong>
      <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
        {alerts.map((a) => (
          <li key={a.alert_id}>
            [{a.severity.toUpperCase()}] {a.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConnectorRow({ record }: { record: SourceHealthRecord }) {
  return (
    <tr data-testid={`connector-row-${record.connector_id}`}>
      <td style={{ padding: "6px 8px", fontWeight: 500 }}>
        {record.display_name}
        {!record.is_healthy && (
          <span style={{ color: "#ef4444", marginLeft: 6, fontSize: "0.75rem" }}>✕ unhealthy</span>
        )}
      </td>
      <td style={{ padding: "6px 8px", color: "var(--color-muted, #71717a)", fontSize: "0.8rem" }}>
        {record.source_type}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <FreshnessChip status={record.freshness_status} />
        {record.freshness_age_minutes != null && (
          <span style={{ marginLeft: 6, fontSize: "0.75rem", color: "var(--color-muted, #71717a)" }}>
            {record.freshness_age_minutes.toFixed(0)} min ago
          </span>
        )}
      </td>
      <td style={{ padding: "6px 8px", fontSize: "0.8rem" }}>
        {record.requests_last_hour}
      </td>
      <td style={{ padding: "6px 8px", fontSize: "0.8rem", color: record.total_errors > 0 ? "#ef4444" : "inherit" }}>
        {record.total_errors}
      </td>
    </tr>
  );
}

export function HealthDashboard({ refreshIntervalMs = 30_000 }: Props) {
  const [data, setData] = useState<HealthDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchDashboard() {
    try {
      const resp = await healthApi.dashboard();
      setData(resp);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchDashboard();
    const id = setInterval(fetchDashboard, refreshIntervalMs);
    return () => clearInterval(id);
  }, [refreshIntervalMs]);

  if (loading && !data) {
    return <div className="panel"><p className="muted">Loading health data…</p></div>;
  }

  if (error) {
    return (
      <div className="panel">
        <p className="error">Health dashboard unavailable: {error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="panel" data-testid="health-dashboard">
      <div className="panel-header">
        <h3 className="panel-title">
          Source Health
          <span
            style={{
              marginLeft: 8,
              display: "inline-block",
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: data.overall_healthy ? "#22c55e" : "#ef4444",
              verticalAlign: "middle",
            }}
            data-testid="health-overall-dot"
          />
        </h3>
        <span style={{ fontSize: "0.75rem", color: "var(--color-muted, #71717a)" }}>
          {data.total_requests_last_hour} req/h
        </span>
      </div>

      <AlertBanner alerts={data.alerts} />

      {data.connectors.length === 0 ? (
        <p className="muted">No connectors registered yet.</p>
      ) : (
        <table
          style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}
          data-testid="health-connector-table"
        >
          <thead>
            <tr style={{ color: "var(--color-muted, #71717a)", fontSize: "0.75rem" }}>
              <th style={{ textAlign: "left", padding: "4px 8px" }}>Connector</th>
              <th style={{ textAlign: "left", padding: "4px 8px" }}>Type</th>
              <th style={{ textAlign: "left", padding: "4px 8px" }}>Freshness</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>Req/h</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>Errors</th>
            </tr>
          </thead>
          <tbody>
            {data.connectors.map((rec) => (
              <ConnectorRow key={rec.connector_id} record={rec} />
            ))}
          </tbody>
        </table>
      )}

      <p style={{ fontSize: "0.7rem", color: "var(--color-muted, #71717a)", marginTop: 8 }}>
        Updated {new Date(data.generated_at).toLocaleTimeString()}
      </p>
    </div>
  );
}
