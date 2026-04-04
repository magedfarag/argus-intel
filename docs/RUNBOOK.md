# Release & Operations Runbook — ARGUS — Multi-Domain Surveillance Intelligence

**Version:** 2.0  
**Last updated:** 2026-04-03  
**P5-4.1 / P5-4.2 deliverable**

---

## 1. Pre-release Checklist

- [ ] All CI checks green on `main` (lint, type-check, unit tests, integration tests)
- [ ] Frontend build clean: `pnpm --filter frontend build`
- [ ] Docker image builds without errors: `docker build -t cam:release .`
- [ ] `.env.example` updated with any new env vars
- [ ] `HANDOVER.md` updated with completed task list
- [ ] Database migrations reviewed and tested against staging DB
- [ ] External connector credentials validated (Sentinel-2, AISStream, OpenSky)
- [ ] Redis connection tested
- [ ] MinIO/S3 bucket accessible

---

## 2. Deployment Steps

### 2.1 Local / Development

```bash
# Install dependencies
pip install -r requirements.txt
pnpm --filter frontend install

# Run migrations
alembic upgrade head

# Start server (auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2.2 Docker Compose (staging / production)

```bash
# Pull latest images
docker compose pull

# Start all services (api + worker + redis + postgres + minio)
docker compose up -d

# Verify health
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/api/v1/health/sources

# Follow logs
docker compose logs -f api worker
```

### 2.3 Environment Variables

All required variables are documented in `.env.example`.  Copy to `.env` and fill in secrets.  
Critical production variables:

| Variable | Purpose |
|----------|---------|
| `API_KEY` | Authentication key (use `openssl rand -hex 32`) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SENTINEL2_CLIENT_ID` / `SENTINEL2_CLIENT_SECRET` | Copernicus credentials |
| `AISSTREAM_API_KEY` | Maritime tracking |
| `OBJECT_STORAGE_ENDPOINT` / `OBJECT_STORAGE_ACCESS_KEY` / `OBJECT_STORAGE_SECRET_KEY` | MinIO/S3 |

### 2.4 Database Migrations

```bash
# Review pending migrations
alembic current
alembic history --verbose

# Apply migrations (always run before starting the service)
alembic upgrade head

# Rollback one step (emergency only)
alembic downgrade -1
```

---

## 3. Rollback Procedure (P5-4.2)

### 3.1 Application rollback

```bash
# Identify the previous image tag
docker images cam --format "{{.Tag}}" | head -5

# Roll back to previous tag
docker compose stop api worker
docker compose up -d --force-recreate api=cam:previous-tag worker=cam:previous-tag

# Verify health
curl http://localhost:8000/healthz
```

### 3.2 Database rollback

```bash
# CAUTION: Only run if the new migration introduced a breaking change
# and no new data has been written to affected tables.

# One step back
alembic downgrade -1

# Specific revision
alembic downgrade <revision-id>
```

### 3.3 Rollback validation checklist

- [ ] `GET /healthz` returns 200
- [ ] `GET /readyz` returns 200 (DB + Redis + S3 green)
- [ ] `POST /api/v1/events/search` returns expected results
- [ ] `GET /api/v1/health/sources` shows connectors healthy
- [ ] No spike in error rate in logs

---

## 4. Post-deployment Validation

```bash
# 1. Liveness + Readiness
curl -s http://localhost:8000/healthz | python -m json.tool
curl -s http://localhost:8000/readyz | python -m json.tool

# 2. API health dashboard
curl -s http://localhost:8000/api/v1/health/sources | python -m json.tool

# 3. Quick event search smoke test
curl -s -X POST http://localhost:8000/api/v1/events/search \
  -H "Content-Type: application/json" \
  -d '{"start_time":"2026-01-01T00:00:00Z","end_time":"2026-03-28T00:00:00Z","limit":5}' \
  | python -m json.tool

# 4. Metrics endpoint
curl -s http://localhost:8000/metrics | head -20
```

---

## 5. Monitoring & Alerts (P5-4.3)

### 5.1 Health endpoints

| Endpoint | Purpose | Expected |
|---------|---------|---------|
| `GET /healthz` | Liveness probe | 200 `{"status":"ok"}` |
| `GET /readyz` | Readiness probe | 200 `{"status":"ready"}` |
| `GET /metrics` | Prometheus metrics | 200, text/plain |
| `GET /api/v1/health/sources` | Source dashboard | 200 JSON |
| `GET /api/v1/health/alerts` | Active SLA alerts | 200 JSON |

### 5.2 Key Prometheus metrics

| Metric | Alert threshold |
|-------|----------------|
| `http_request_duration_seconds_p95` | > 500 ms |
| `http_requests_total{status="5xx"}` | Rate > 1% of total |
| `celery_task_failed_total` | Rate > 0 for 5 min |

### 5.3 Recommended Prometheus alert rules

```yaml
# prometheus/alerts.yml
groups:
  - name: cam_api
    rules:
      - alert: HighAPILatency
        expr: histogram_quantile(0.95, http_request_duration_seconds_bucket) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API p95 latency > 500ms"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "API error rate > 1%"
```

---

## 6. Performance Baselines (P5-1.7)

Run load tests to establish baselines before each release:

```bash
pip install locust
locust -f tests/load/locustfile.py --host http://localhost:8000 \
       --headless -u 50 -r 10 --run-time 120s \
       --html reports/load_test_$(date +%Y%m%d).html
```

**Target thresholds:**

| Endpoint | p50 | p95 | Error rate |
|---------|-----|-----|-----------|
| `POST /api/v1/events/search` | < 100 ms | < 200 ms | < 0.1% |
| `GET /api/v1/health/sources` | < 50 ms | < 100 ms | 0% |
| `GET /api/v1/events/timeline` | < 80 ms | < 150 ms | < 0.1% |

---

## 7. Incident Response Runbooks (P6 Track C)

### 7.1 Connector Is Down

**Symptoms:** `GET /api/v1/health/connectors` shows `status: degraded` for one
or more connectors; ingestion lag alerts firing.

**Diagnosis:**

```bash
# Identify the degraded connector(s)
curl -s http://localhost:8000/api/v1/health/connectors | python -m json.tool

# Inspect the error message
curl -s http://localhost:8000/api/v1/health/connectors \
  | python -c "import sys,json; [print(c['connector_id'], c['status'], c.get('error_count')) for c in json.load(sys.stdin)['connectors']]"

# Follow connector-specific log lines
docker compose logs -f api | grep -i "<connector-id>"
```

**Recovery:**

1. Verify external service availability (check provider status page, try manual
   `curl` to the upstream API URL).
2. Confirm credentials are valid.  Rotate if expired.
3. Re-enable after manual validation:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/health/sources/<connector-id>/enable
   ```
4. Monitor for 5 minutes; confirm `consecutive_errors` drops to 0.

**Safe retry intervals:**

| Connector | Minimum retry interval |
|---|---|
| GDELT | 5 min (public rate limit) |
| OpenSky | 10 min (unauthenticated: 1 req / 10 min) |
| AISStream | 30 s (WebSocket; reconnect immediately on drop) |
| Sentinel-2 / Landsat STAC | 2 min |

---

### 7.2 Replay Query Is Slow

**Symptoms:** `replay_query_duration_seconds p95 > 3 s`; users report timeline
lag; `ALERT-03` firing.

**Diagnosis:**

```bash
# Confirm metrics
curl -s http://localhost:8000/api/v1/health/metrics | python -m json.tool | grep replay

# Get current event store approximate size
curl -s http://localhost:8000/api/v1/events/search \
  -X POST -H "Content-Type: application/json" \
  -d '{"start_time":"2020-01-01T00:00:00Z","end_time":"2030-01-01T00:00:00Z","limit":1}' \
  | python -m json.tool | grep total_count
```

**Recovery:**

1. **Narrow the query window:** ask the client to reduce the time range.
2. **Flush materialization cache** (if applicable):
   ```bash
   # Example: clear Python in-memory cache via rolling restart
   docker compose restart api
   ```
3. **Throttle background pollers** by increasing `GDELT_POLL_INTERVAL_MINUTES`
   and `OPENSKY_POLL_INTERVAL_SECONDS` in `.env` and restarting workers.
4. **Prune old events:** reduce `EVENT_STORE_MAX_EVENTS` in config and restart
   (events older than the trim point are evicted from memory; they are NOT
   permanently deleted if raw payload references exist in object storage).

---

### 7.3 Audit Log Failures

**Symptoms:** `ALERT-08` fired; log line `audit_log_write_failed`; `GET /readyz`
reports `audit: error`.

**Diagnosis:**

```bash
# Check readiness — look for audit/storage fields
curl -s http://localhost:8000/readyz | python -m json.tool

# Verify object storage connectivity
docker compose exec api python -c "
import boto3, os
s3 = boto3.client('s3',
    endpoint_url=os.getenv('OBJECT_STORAGE_ENDPOINT'),
    aws_access_key_id=os.getenv('OBJECT_STORAGE_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('OBJECT_STORAGE_SECRET_KEY'))
print(s3.list_buckets())
"
```

**Recovery:**

1. If object storage is unreachable: verify endpoint, credentials, and network
   policy.  Rotate keys if needed.
2. Audit events are also emitted to structured stdout in JSON format.  Ensure
   the log shipper (Fluentd / Logstash / Loki) is collecting them so no events
   are permanently lost during the storage outage.
3. Once storage is restored, replay audit events from the log shipper's buffer
   into the `audit/` bucket prefix manually.
4. Do not delete or truncate any audit log files without security-team approval.

**Manual recovery steps** (rare — only when the primary write path is broken
permanently):

```bash
# Collect audit lines from container logs
docker compose logs api | grep '"type":"audit"' > /tmp/audit_recovery.jsonl

# Upload to the audit bucket
aws s3 cp /tmp/audit_recovery.jsonl s3://<bucket>/audit/recovery_$(date +%Y%m%d).jsonl
```

---

### 7.4 Memory Store Full

**Symptoms:** `ALERT-07` critical; API responses become slow or return 500;
RSS > 95% of `MEMORY_LIMIT_MB`.

**Diagnosis:**

```bash
# RSS of the API process
docker stats argus_api --no-stream --format "{{.MemUsage}}"

# Number of events in store (approximate)
curl -s -X POST http://localhost:8000/api/v1/events/search \
  -H "Content-Type: application/json" \
  -d '{"start_time":"2020-01-01T00:00:00Z","end_time":"2030-01-01T00:00:00Z","limit":1}' \
  | python -m json.tool | grep total_count
```

**Graceful eviction:**

1. Set `EVENT_STORE_MAX_EVENTS` to a lower value in `.env`.
2. Perform a rolling restart of the API container:
   ```bash
   docker compose up -d --force-recreate api
   ```
3. The EventStore will not accept events beyond `max_events`; oldest events are
   evicted automatically on next ingest cycle.

**Emergency restart procedure:**

```bash
# Warn users before restarting — in-memory state is lost
docker compose stop api worker
docker compose up -d api worker

# Verify recovery
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/api/v1/health/connectors
```

> ⚠ All in-memory data (events, investigations, AOI state) is **lost** on
> restart unless persisted to Postgres / object storage.  See
> `docs/DISASTER_RECOVERY.md` for the data-loss implications and the path
> to durable storage.

---

### 7.5 Full Restart Procedure

Use this procedure for planned maintenance restarts or after a critical incident.

```bash
# 1. Notify users (update status page)

# 2. Drain in-flight requests — wait for active connections to close
#    (configure a SIGTERM grace period in docker-compose.yml: stop_grace_period: 30s)

# 3. Stop services in dependency order
docker compose stop api worker

# 4. Optional: export in-memory state before restart
curl -s -X POST http://localhost:8000/api/v1/export/events \
  -H "Content-Type: application/json" \
  -d '{"format":"parquet","start_time":"2000-01-01T00:00:00Z","end_time":"2099-01-01T00:00:00Z"}' \
  -o /tmp/pre_restart_export.parquet

# 5. Restart
docker compose up -d api worker

# 6. Health verification
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl -s http://localhost:8000/api/v1/health/connectors \
  | python -m json.tool | grep '"status"'
curl -s http://localhost:8000/api/v1/health/metrics | python -m json.tool

# 7. Run smoke test suite
pytest tests/unit/test_startup_smoke.py -q
```

---

### 7.6 Rollback Procedure

See also §3 (Rollback Procedure) for the Docker image rollback steps.

**Data safety before rollback:**

1. Export all active investigations:
   ```bash
   for id in $(curl -s http://localhost:8000/api/v1/investigations \
       | python -c "import sys,json; [print(i['id']) for i in json.load(sys.stdin)['items']]"); do
     curl -s http://localhost:8000/api/v1/investigations/$id/export > /tmp/inv_$id.json
   done
   ```
2. Export event data:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/export/events \
     -H "Content-Type: application/json" \
     -d '{"format":"json"}' -o /tmp/events_before_rollback.json
   ```
3. Note the current Alembic revision:
   ```bash
   alembic current
   ```
4. Roll back the container (see §3.1).
5. If the DB schema changed, roll back the migration:
   ```bash
   alembic downgrade -1
   ```
6. Validate with the post-deployment checklist (§4).
7. Re-import critical investigations from the exported JSON files if needed.
