# ARGUS — Alerting Rules

**Version:** 1.0  
**Phase:** 6 Track C  
**Last updated:** 2026-04-04

This document defines the minimum set of operational alerts for the ARGUS
Multi-Domain Surveillance Intelligence platform.  Rules are expressed as
human-readable conditions; translate to your alerting backend
(Prometheus AlertManager, Datadog, Grafana, PagerDuty, etc.) as needed.

---

## Alert Rule Catalogue

### ALERT-01 — High Ingestion Lag

| Field | Value |
|---|---|
| **Name** | `ArgusIngestionLagHigh` |
| **Condition** | `ingestion_lag_seconds p95 > 300` for any source family (`ais`, `opensky`, `gdelt`, `imagery`) for 5 consecutive minutes |
| **Severity** | `warning` when lag > 5 min; `critical` when lag > 15 min |
| **Recommended Action** | 1. Check connector health: `GET /api/v1/health/connectors` — identify the source family with high lag. 2. Inspect worker logs for the relevant poller task (`poll_aisstream_positions`, `poll_opensky_positions`, `poll_gdelt_context`). 3. Verify network connectivity to upstream API. 4. If the Celery worker is stalled, restart it: `docker compose restart worker`. 5. If lag persists > 30 min, escalate to on-call. |

---

### ALERT-02 — Connector Error Spike

| Field | Value |
|---|---|
| **Name** | `ArgusConnectorErrorSpike` |
| **Condition** | `connector_error_count` increments > 10 times within any 1-hour rolling window for a single connector |
| **Severity** | `warning` |
| **Recommended Action** | 1. Check `GET /api/v1/health/connectors` for the connector's `consecutive_errors` and `last_error_message`. 2. Verify external API status pages (AISStream, OpenSky, GDELT, STAC catalogs). 3. Check for expired or revoked credentials (Sentinel-2, Maxar, Planet). 4. Reduce poll frequency if rate-limited. 5. Disable the connector temporarily via `POST /api/v1/health/sources/{id}/disable` to suppress cascading errors. |

---

### ALERT-03 — Slow Replay Queries

| Field | Value |
|---|---|
| **Name** | `ArgusReplayQuerySlow` |
| **Condition** | `replay_query_duration_seconds p95 > 3.0` over a 5-minute window |
| **Severity** | `warning` |
| **Recommended Action** | 1. Check current event store size and whether it exceeds the in-memory limit. 2. Flush the materialization cache if present: `POST /api/v1/cache/flush` (when available). 3. Reduce the query window in the client request (`start_time` / `end_time` bounds). 4. If the store has grown unbounded, perform a controlled restart to reset in-memory state (data loss for unsaved events — notify users first). 5. Long-term: migrate to Postgres + indexed queries (see `docs/DISASTER_RECOVERY.md`). |

---

### ALERT-04 — Active Investigation Count Drop

| Field | Value |
|---|---|
| **Name** | `ArgusInvestigationCountDrop` |
| **Condition** | `active_investigations_total` drops by > 20% compared to the previous 10-minute sample AND remains lower for 2 consecutive samples |
| **Severity** | `critical` |
| **Recommended Action** | 1. Confirm the drop is not caused by legitimate user deletions (check audit log). 2. If the service was restarted, in-memory investigations are **lost** — this is a known limitation (see `docs/DISASTER_RECOVERY.md`). 3. Advise users to re-create investigations from exported JSON evidence packs that were saved before the restart. 4. If the drop was unintentional, restore from the most recent JSON export in the configured object storage bucket. 5. Escalate immediately if no exports are available. |

---

### ALERT-05 — Evidence Pack Export Failures

| Field | Value |
|---|---|
| **Name** | `ArgusEvidencePackExportFailure` |
| **Condition** | Evidence pack export error events > 3 within a 1-hour rolling window |
| **Severity** | `warning` |
| **Recommended Action** | 1. Check API logs for `POST /api/v1/evidence-packs` errors. 2. Verify object storage (MinIO/S3) connectivity and write permissions: `GET /readyz` should report `storage: ok`. 3. Check available disk space on the storage backend. 4. If S3/MinIO credentials have expired, rotate them and restart the API. 5. Manually retry failed exports by re-triggering the export endpoint. |

---

### ALERT-06 — High API Error Rate

| Field | Value |
|---|---|
| **Name** | `ArgusAPIErrorRateHigh` |
| **Condition** | HTTP 5xx responses > 5% of total requests over any 5-minute window |
| **Severity** | `critical` |
| **Recommended Action** | 1. Check `GET /api/health` for internal component status (circuit breaker, cache, DB). 2. Inspect structured logs for the most frequent error class / route. 3. If the circuit breaker is open, wait for `circuit_breaker_recovery_timeout` or force-close via config. 4. If unhandled Python exceptions appear, redeploy the last known-good image (see Runbook section 3). 5. Notify users of degraded service via status page. |

---

### ALERT-07 — Memory Store Near Limit

| Field | Value |
|---|---|
| **Name** | `ArgusMemoryStoreNearLimit` |
| **Condition** | Resident set size (RSS) of the API process > 80% of `MEMORY_LIMIT_MB` setting, OR event store size exceeds `max_events` configured threshold |
| **Severity** | `warning` at 80%; `critical` at 95% |
| **Recommended Action** | 1. Check `GET /api/v1/health/connectors` and `/api/health` for store size indicators. 2. Trim in-memory stores by reducing active AOIs or shortening the retention window. 3. Trigger graceful eviction of oldest events: adjust `event_store_max_events` in config and restart. 4. If at critical threshold, perform an emergency controlled restart (see Runbook — Memory Store Full). 5. Long-term: migrate to Postgres-backed persistence to remove in-memory size constraints. |

---

### ALERT-08 — Audit Log Write Failure

| Field | Value |
|---|---|
| **Name** | `ArgusAuditLogWriteFailure` |
| **Condition** | Any audit log write exception is logged (log line contains `audit_log_write_failed`) OR `GET /readyz` reports `audit: error` |
| **Severity** | `critical` |
| **Recommended Action** | 1. Check object storage (MinIO/S3) write access — audit logs are appended to `audit/` prefix in the configured bucket. 2. Verify storage credentials and bucket policy. 3. If storage is unavailable, audit logs fall back to structured stdout — ensure log shipping (Fluentd, Logstash, Loki) is capturing them. 4. Do not clear or truncate audit logs without authorization. 5. Escalate to security team if audit loss exceeds the acceptable window defined in the data retention policy. |

---

## Severity Reference

| Severity | Response SLA | Paging |
|---|---|---|
| `critical` | Acknowledge within 15 min | Yes — PagerDuty / on-call |
| `warning` | Acknowledge within 2 hours | Slack / team channel only |

---

## Prometheus Expression Examples

```yaml
# prometheus/alerts.yml
groups:
  - name: argus_track_c
    rules:

      - alert: ArgusIngestionLagHigh
        expr: >
          histogram_quantile(0.95,
            rate(ingestion_lag_seconds_bucket[5m])
          ) > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Ingestion lag p95 > 5 min for {{ $labels.source_family }}"

      - alert: ArgusConnectorErrorSpike
        expr: >
          increase(connector_error_count[1h]) > 10
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "Connector {{ $labels.connector }} has > 10 errors in the last hour"

      - alert: ArgusReplayQuerySlow
        expr: >
          histogram_quantile(0.95,
            rate(replay_query_duration_seconds_bucket[5m])
          ) > 3.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Replay query p95 latency > 3 s"

      - alert: ArgusAPIErrorRateHigh
        expr: >
          rate(http_requests_total{status=~"5.."}[5m])
          / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "API 5xx error rate > 5%"
```

> **Note:** The ARGUS demo deployment uses the lightweight in-process metrics
> registry (`app/metrics.py`) rather than a Prometheus push-gateway.  The
> PromQL expressions above apply when `prometheus_fastapi_instrumentator` +
> `prometheus_client` are installed in a production deployment.

---

*Owned by: Platform Engineering / On-Call Rotation*  
*Review cadence: quarterly or after any P0/P1 incident*
