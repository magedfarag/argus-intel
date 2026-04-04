# On-Call Handoff Document — ARGUS — Multi-Domain Surveillance Intelligence

**Version:** 2.0  
**Last updated:** 2026-04-03  
**P5-4.5 deliverable**

---

## Service Overview

The ARGUS Intelligence Platform is a geospatial intelligence platform that monitors
construction activity using satellite imagery, maritime/aviation tracking, and contextual
events. It runs as a FastAPI backend + React frontend, backed by PostgreSQL/PostGIS,
Redis, and MinIO object storage.

**Architecture:** `docs/ARCHITECTURE.md`  
**API reference:** `docs/API.md`  
**Full runbook:** `docs/RUNBOOK.md`

---

## Escalation Contacts

| Role | Responsibility | Contact |
|------|---------------|---------|
| Platform Lead | Architecture decisions, incident command | See team directory |
| Backend Engineer | API, connectors, Celery workers | See team directory |
| DevOps | Infrastructure, Docker, CI/CD | See team directory |
| Data/Analytics | GDELT, AIS, change analytics | See team directory |

---

## Quick Diagnostic Commands

```bash
# 1. Check service health
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz

# 2. Check source dashboard for stale/failing connectors
curl http://localhost:8000/api/v1/health/sources

# 3. Check active SLA alerts
curl http://localhost:8000/api/v1/health/alerts

# 4. Check Docker container status
docker compose ps

# 5. Check logs (last 100 lines)
docker compose logs --tail=100 api
docker compose logs --tail=100 worker

# 6. Check Celery worker status
docker compose exec worker celery -A app.workers.celery_app inspect active
```

---

## Common Incidents & Remediation

### INC-001: API returning 500 errors

1. Check `GET /readyz` — if PostgreSQL or Redis is unhealthy, that is root cause
2. Check `docker compose logs api` for exception traceback
3. If DB unreachable: verify `DATABASE_URL` env var; check Postgres container
4. If Redis unreachable: verify `REDIS_URL`; check Redis container
5. Restart: `docker compose restart api`

### INC-002: Celery workers not processing jobs

1. `docker compose logs worker` — look for connection errors
2. Verify Redis is up: `docker compose exec redis redis-cli ping`
3. Check beat schedule: `docker compose exec worker celery -A app.workers.celery_app inspect scheduled`
4. Restart worker: `docker compose restart worker`

### INC-003: GDELT connector failing to poll

1. Check `GET /api/v1/health/sources` — look for `gdelt` connector status
2. GDELT DOC API is public; failures usually indicate network issues
3. Check `app/workers/tasks:poll_gdelt_context` logs
4. The `contextual_event_count` will drop; no data loss risk (GDELT is a refetch)

### INC-004: AIS/OpenSky data stale

1. Check connector health dashboard for `aisstream` / `opensky` entries
2. AISStream requires a valid `AISSTREAM_API_KEY` — verify `.env`
3. OpenSky free tier has rate limits — check `requests_last_hour` in dashboard
4. Celery beat schedule: `poll-opensky-every-60s` and `poll-aisstream-every-30s`

### INC-005: High API latency

1. Check `/metrics` endpoint for `http_request_duration_seconds` histogram
2. Run load test: `locust -f tests/load/locustfile.py --host http://localhost:8000 --headless -u 10 -r 2 --run-time 30s`
3. Check Redis cache hit rate (logs show "Cache backend" stats)
4. Review PostGIS query plans if `DATABASE_URL` is configured (use `EXPLAIN ANALYZE`)

### INC-006: Database migrations failed

1. Check current state: `alembic current`
2. Review migration history: `alembic history --verbose`
3. If migration broke mid-way, manually check which tables were created
4. Rollback: `alembic downgrade -1` (only safe if no new data in affected tables)
5. Fix migration script and re-apply: `alembic upgrade head`

---

## Change Detection Quality Issues

### FP-001: Cloud shadow false positives
- Connector: `Sentinel2Provider`, `LandsatProvider`
- Mitigation: Raise `cloud_cover_threshold` in AppSettings (`DEFAULT_CLOUD_THRESHOLD`)
- Reference: `docs/CHANGE_DETECTION.md` §3.1

### FP-002: Sensor cross-calibration artifacts
- Occurs when before/after scenes are from different sensors
- Mitigation: `ImageryCompareResponse.cross_sensor_note` flags these
- Analyst action: Dismiss candidates with cross-sensor flag unless confidence > 0.85

---

## Data Retention Policy

- Telemetry (AIS/ADS-B): 30-day rolling window, then purged by `enforce_telemetry_retention` Celery task
- Analyst-reviewed change candidates: retained indefinitely (audit trail)
- Export jobs: 1-hour in-memory TTL; files are regenerated on demand
- Canonical events: duration based on PostGIS retention (manual purge via `pg_partman` in P5+)

---

## License / Compliance Notes

- **GDELT**: Open / CC BY 4.0 — redistribution allowed for non-commercial
- **OpenSky**: Non-commercial research use only — export filters enforce this
- **AISStream**: Depends on subscription tier — check license.redistribution field
- **Sentinel-2**: ESA Open Data — free redistribution with attribution
- **Landsat**: USGS public domain — unrestricted

Export service enforces `license.redistribution` filtering by default.  
To include restricted data, the caller must set `include_restricted=true` (admin role, P5-3.3).

---

## Known Limitations (as of 2026-04-03)

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| In-memory event/AOI store | Data lost on restart | PostGIS persistence (P0-4 migration path ready) |
| AIS/OpenSky coverage uneven in ME | Gaps in maritime/aviation tracking | Source health dashboard shows gap visually |
| GDELT country resolution is centroid-based | Events may be misclassified near borders | Analysts should treat GDELT as corroborative only |
| Change detection uses flat-earth area approximation | < 5% error on small AOIs (<50 km²) | Acceptable for pilot; replace with Haversine in P6 |
