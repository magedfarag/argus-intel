# Release & Operations Runbook — Construction Activity Monitor

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
