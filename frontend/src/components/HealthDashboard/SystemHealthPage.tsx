/**
 * SystemHealthPage — unified health monitoring for all internal and external components.
 *
 * Sections:
 *   1. Overall status banner
 *   2. Infrastructure (Redis, PostgreSQL, Celery, App Mode)
 *   3. Satellite Providers (Sentinel-2, Landsat, Maxar, Planet, Demo)
 *   4. Data Connectors (AIS, OpenSky, GDELT, Earth Search, Planetary Computer)
 *   5. Active Alerts
 *
 * Data sources:
 *   GET /api/health          → infrastructure + provider availability
 *   GET /api/providers       → provider details
 *   GET /api/v1/health/sources → connector freshness + error counts
 *   GET /api/v1/health/alerts  → active alerts
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { healthApi, systemApi } from "../../api/client";
import type {
  HealthDashboardResponse,
  HealthAlert,
  SourceHealthRecord,
} from "../../api/types";
import "./SystemHealthPage.css";

const REFRESH_MS = 30_000;

// ── Shape of /api/health ─────────────────────────────────────────────────────
interface InfraHealth {
  status: string;
  mode: string;
  demo_available: boolean;
  redis: string;
  celery_worker: string;
  providers: Record<string, string>;
  version?: string;
  circuit_breakers: Record<string, string>;
  job_manager: string;
  cache_stats: { hits: number; misses: number; hit_rate: number; backend: string };
  database: string;
  object_storage: string;
}

// ── Shape of /api/providers ──────────────────────────────────────────────────
interface ProviderDetail {
  name: string;
  display_name: string;
  available: boolean;
  reason?: string;
  resolution_m?: number;
}

// ── Status chip helpers ──────────────────────────────────────────────────────
type StatusLevel = "ok" | "warn" | "error" | "unknown";

function toLevel(value: string): StatusLevel {
  if (!value) return "unknown";
  const v = value.toLowerCase();
  if (v === "ok" || v === "alive" || v === "true" || v === "available") return "ok";
  if (v.startsWith("unavailable") || v === "unreachable" || v === "false") return "error";
  if (v === "no_workers" || v === "not_configured") return "warn";
  return "unknown";
}

function freshnessLevel(status: string): StatusLevel {
  if (status === "fresh") return "ok";
  if (status === "stale") return "warn";
  if (status === "critical") return "error";
  return "unknown";
}

function cbLevel(state: string): StatusLevel {
  if (state === "closed") return "ok";
  if (state === "half_open") return "warn";
  if (state === "open") return "error";
  return "unknown";
}

function depLevel(value: string): StatusLevel {
  if (!value) return "unknown";
  if (value === "ok") return "ok";
  if (value === "not_configured") return "unknown";
  if (value.startsWith("error") || value === "unreachable" || value === "check_failed") return "error";
  return "warn";
}

const LEVEL_COLOR: Record<StatusLevel, string> = {
  ok: "var(--accent-green)",
  warn: "var(--accent-amber)",
  error: "var(--accent-red)",
  unknown: "var(--text-muted)",
};

const LEVEL_BG: Record<StatusLevel, string> = {
  ok: "rgba(76,175,80,0.12)",
  warn: "rgba(245,158,11,0.12)",
  error: "rgba(239,68,68,0.12)",
  unknown: "rgba(100,116,139,0.08)",
};

const LEVEL_LABEL: Record<StatusLevel, string> = {
  ok: "OK",
  warn: "WARN",
  error: "ERROR",
  unknown: "—",
};

function StatusDot({ level }: { level: StatusLevel }) {
  return (
    <span
      className="sh-dot"
      style={{ background: LEVEL_COLOR[level] }}
      aria-label={LEVEL_LABEL[level]}
    />
  );
}

function StatusBadge({ level, label }: { level: StatusLevel; label?: string }) {
  return (
    <span
      className="sh-badge"
      style={{
        background: LEVEL_BG[level],
        color: LEVEL_COLOR[level],
        border: `1px solid ${LEVEL_COLOR[level]}33`,
      }}
    >
      {label ?? LEVEL_LABEL[level]}
    </span>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h4 className="sh-section-title">{children}</h4>;
}

function Row({
  label,
  detail,
  level,
  badge,
  sub,
}: {
  label: string;
  detail?: string;
  level: StatusLevel;
  badge?: string;
  sub?: string;
}) {
  return (
    <div className="sh-row">
      <StatusDot level={level} />
      <span className="sh-row-label">{label}</span>
      {sub && <span className="sh-row-sub">{sub}</span>}
      <span className="sh-row-spacer" />
      {detail && <span className="sh-row-detail">{detail}</span>}
      <StatusBadge level={level} label={badge} />
    </div>
  );
}

function OverallBanner({ level }: { level: StatusLevel }) {
  const msgs: Record<StatusLevel, string> = {
    ok: "All systems operational",
    warn: "Degraded — some components need attention",
    error: "Outage detected — one or more critical components are down",
    unknown: "Health status unknown",
  };
  return (
    <div
      className="sh-banner"
      style={{
        background: LEVEL_BG[level],
        borderColor: LEVEL_COLOR[level] + "66",
        color: LEVEL_COLOR[level],
      }}
      data-testid="sh-banner"
    >
      <StatusDot level={level} />
      <span className="sh-banner-text">{msgs[level]}</span>
    </div>
  );
}

function AlertList({ alerts }: { alerts: HealthAlert[] }) {
  const active = alerts.filter((a) => !a.resolved);
  if (active.length === 0) return null;
  return (
    <div className="sh-card" data-testid="sh-alerts">
      <SectionTitle>Active Alerts ({active.length})</SectionTitle>
      <div className="sh-alert-list">
        {active.map((a) => (
          <div
            key={a.alert_id}
            className="sh-alert-item"
            style={{
              borderLeftColor: a.severity === "critical" ? "var(--accent-red)" : "var(--accent-amber)",
            }}
          >
            <span
              className="sh-badge"
              style={{
                background: a.severity === "critical" ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)",
                color: a.severity === "critical" ? "var(--accent-red)" : "var(--accent-amber)",
                border: "none",
              }}
            >
              {a.severity.toUpperCase()}
            </span>
            <span className="sh-alert-msg">{a.message}</span>
            <span className="sh-row-detail">
              {new Date(a.triggered_at).toLocaleTimeString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export function SystemHealthPage() {
  const [infra, setInfra] = useState<InfraHealth | null>(null);
  const [providers, setProviders] = useState<ProviderDetail[]>([]);
  const [connectors, setConnectors] = useState<HealthDashboardResponse | null>(null);
  const [alerts, setAlerts] = useState<HealthAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async () => {
    const newErrors: Record<string, string> = {};

    const [infraRes, providersRes, connRes, alertsRes] = await Promise.allSettled([
      systemApi.fullHealth() as Promise<InfraHealth>,
      systemApi.providers() as Promise<{ providers: ProviderDetail[] }>,
      healthApi.dashboard(),
      healthApi.alerts(false),
    ]);

    if (infraRes.status === "fulfilled") setInfra(infraRes.value);
    else newErrors.infra = infraRes.reason?.message ?? String(infraRes.reason);

    if (providersRes.status === "fulfilled") setProviders(providersRes.value.providers ?? []);
    else newErrors.providers = providersRes.reason?.message ?? String(providersRes.reason);

    if (connRes.status === "fulfilled") setConnectors(connRes.value);
    else newErrors.connectors = connRes.reason?.message ?? String(connRes.reason);

    if (alertsRes.status === "fulfilled") setAlerts(alertsRes.value);
    else newErrors.alerts = alertsRes.reason?.message ?? String(alertsRes.reason);

    setErrors(newErrors);
    setLastRefresh(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    timerRef.current = setInterval(fetchAll, REFRESH_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAll]);

  // ── Compute overall level ───────────────────────────────────────────────
  function computeOverall(): StatusLevel {
    if (loading) return "unknown";
    const redisLevel = infra ? toLevel(infra.redis) : "unknown";
    const activeAlerts = alerts.filter((a) => !a.resolved);
    const hasCritical =
      activeAlerts.some((a) => a.severity === "critical") ||
      redisLevel === "error" ||
      (infra && depLevel(infra.database) === "error") ||
      (infra && Object.values(infra.circuit_breakers).some((s) => s === "open"));
    const hasWarn =
      activeAlerts.some((a) => a.severity === "warning") ||
      redisLevel === "warn" ||
      (infra && toLevel(infra.celery_worker) === "warn") ||
      (infra && Object.values(infra.circuit_breakers).some((s) => s === "half_open")) ||
      (connectors?.connectors.some((c) => !c.is_healthy) ?? false);
    if (hasCritical) return "error";
    if (hasWarn) return "warn";
    return "ok";
  }

  const overallLevel = computeOverall();

  if (loading) {
    return (
      <div className="sh-page">
        <div className="sh-loading">Fetching health data…</div>
      </div>
    );
  }

  return (
    <div className="sh-page" data-testid="system-health-page">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="sh-header">
        <div>
          <h2 className="sh-title">System Health</h2>
          {lastRefresh && (
            <span className="sh-refresh-time">
              Updated {lastRefresh.toLocaleTimeString()} · auto-refresh {REFRESH_MS / 1000}s
            </span>
          )}
        </div>
        <button className="btn btn-sm" onClick={fetchAll} title="Refresh now">
          ↺ Refresh
        </button>
      </div>

      <OverallBanner level={overallLevel} />

      {Object.keys(errors).length > 0 && (
        <div className="sh-fetch-errors">
          {Object.entries(errors).map(([k, v]) => (
            <div key={k} className="sh-fetch-error">
              Failed to load <strong>{k}</strong>: {v}
            </div>
          ))}
        </div>
      )}

      {/* ── Alerts ─────────────────────────────────────────────── */}
      <AlertList alerts={alerts} />

      <div className="sh-grid">
        {/* ── Infrastructure ───────────────────────────────────── */}
        <div className="sh-card" data-testid="sh-infrastructure">
          <SectionTitle>Infrastructure</SectionTitle>

          <Row
            label="Redis / Cache"
            level={infra ? toLevel(infra.redis) : "unknown"}
            badge={infra?.redis ?? "—"}
            sub={infra?.cache_stats ? `${(infra.cache_stats.hit_rate * 100).toFixed(0)}% hit rate` : ""}
          />
          <Row
            label="Celery Worker"
            level={infra ? toLevel(infra.celery_worker) : "unknown"}
            badge={infra?.celery_worker ?? "—"}
            sub="async task queue"
          />
          <Row
            label="PostgreSQL"
            level={infra ? depLevel(infra.database) : "unknown"}
            badge={infra?.database ?? "—"}
            sub="persistent storage"
          />
          <Row
            label="Object Storage"
            level={infra ? depLevel(infra.object_storage) : "unknown"}
            badge={infra?.object_storage ?? "—"}
            sub="S3 / MinIO"
          />
          <Row
            label="Job Manager"
            level={infra?.job_manager === "memory" ? "warn" : infra?.job_manager ? "ok" : "unknown"}
            badge={infra?.job_manager ?? "—"}
            sub="job persistence"
          />
          <Row
            label="App Mode"
            level="ok"
            badge={infra?.mode ?? "—"}
            sub="provider behaviour"
          />
        </div>

        {/* ── Satellite Providers ─────────────────────────────── */}
        <div className="sh-card" data-testid="sh-providers">
          <SectionTitle>Satellite Providers</SectionTitle>
          {providers.length === 0 ? (
            <p className="sh-empty">
              {errors.providers ? `Unavailable: ${errors.providers}` : "No providers registered."}
            </p>
          ) : (
            providers.map((p) => (
              <Row
                key={p.name}
                label={p.display_name}
                level={p.available ? "ok" : p.name === "demo" ? "ok" : "error"}
                badge={p.available ? "available" : "unavailable"}
                sub={p.resolution_m ? `${p.resolution_m} m` : undefined}
                detail={!p.available && p.reason ? p.reason : undefined}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Circuit Breakers ─────────────────────────────────────── */}
      {infra && Object.keys(infra.circuit_breakers).length > 0 && (
        <div className="sh-card" data-testid="sh-circuit-breakers">
          <SectionTitle>Circuit Breakers</SectionTitle>
          <div className="sh-cb-grid">
            {Object.entries(infra.circuit_breakers).map(([name, state]) => (
              <Row
                key={name}
                label={name}
                level={cbLevel(state)}
                badge={state}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Data Connectors ──────────────────────────────────────── */}
      <div className="sh-card" data-testid="sh-connectors">
        <div className="sh-connectors-header">
          <SectionTitle>Data Connectors</SectionTitle>
          {connectors && (
            <span className="sh-refresh-time">
              {connectors.total_requests_last_hour} req/h ·{" "}
              {connectors.total_errors_last_hour} err/h
            </span>
          )}
        </div>

        {errors.connectors ? (
          <p className="sh-empty">Unavailable: {errors.connectors}</p>
        ) : !connectors || connectors.connectors.length === 0 ? (
          <p className="sh-empty">No connectors registered.</p>
        ) : (
          <div className="sh-connector-grid">
            {connectors.connectors.map((c) => (
              <ConnectorCard key={c.connector_id} record={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ConnectorCard({ record }: { record: SourceHealthRecord }) {
  const level = record.is_healthy ? freshnessLevel(record.freshness_status) : "error";

  return (
    <div
      className="sh-connector-card"
      style={{ borderLeftColor: LEVEL_COLOR[level] }}
      data-testid={`sh-connector-${record.connector_id}`}
    >
      <div className="sh-connector-top">
        <StatusDot level={level} />
        <span className="sh-connector-name">{record.display_name}</span>
        <StatusBadge
          level={level}
          label={record.is_healthy ? record.freshness_status : "down"}
        />
      </div>
      <div className="sh-connector-meta">
        <span className="sh-tag">{record.source_type}</span>
        {record.freshness_age_minutes != null && (
          <span className="sh-row-detail">
            {record.freshness_age_minutes < 60
              ? `${record.freshness_age_minutes.toFixed(0)} min ago`
              : `${(record.freshness_age_minutes / 60).toFixed(1)} h ago`}
          </span>
        )}
      </div>
      {record.consecutive_errors > 0 && (
        <div className="sh-connector-errors">
          {record.consecutive_errors} consecutive error{record.consecutive_errors > 1 ? "s" : ""}
          {record.last_error_message && (
            <span className="sh-error-msg" title={record.last_error_message}>
              {" "}— {record.last_error_message.slice(0, 60)}
              {record.last_error_message.length > 60 ? "…" : ""}
            </span>
          )}
        </div>
      )}
      <div className="sh-connector-stats">
        <span>{record.requests_last_hour} req/h</span>
        <span style={{ color: record.total_errors > 0 ? "var(--accent-red)" : "inherit" }}>
          {record.total_errors} total err
        </span>
      </div>
    </div>
  );
}
