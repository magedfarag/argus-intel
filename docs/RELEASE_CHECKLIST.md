# Release Checklist — ARGUS Multi-Domain Surveillance Intelligence

**Version:** 6.0.0  
**Date:** 2026-04-04  
**Purpose:** Manual gate checklist for release engineers before cutting a production release.

An engineer must personally verify every item and record their initials and the verification timestamp before the release is approved.

---

## 1. Code Quality

- [ ] `npx tsc --noEmit` exits clean (0 TypeScript errors) in `frontend/`
- [ ] `python -m pytest tests/ -q` passes with ≥1400 tests passing and 0 failures
- [ ] No `TODO`, `FIXME`, or `STUB` comments in any production code path (`app/`, `src/`)
- [ ] `ruff check app/ src/` (or equivalent linter) exits clean
- [ ] `pip-audit` shows no known vulnerabilities in `requirements.txt`
- [ ] All Pydantic v2 models use `model_validator(mode='after')` (no v1 compat shim warnings)
- [ ] No hardcoded secrets, credentials, or real API keys in any committed file

---

## 2. Security

- [ ] RBAC is enforced on all mutation endpoints (`POST`, `PUT`, `DELETE`) — verify `require_operator` or `require_admin` on every write route in `src/api/`
- [ ] `AuditLoggingMiddleware` is registered in `app/main.py` and active in staging
- [ ] `API_KEY` env var is set in the production `.env` (not left empty)
- [ ] `ALLOWED_ORIGINS` is restricted to the actual frontend domain (not `*`)
- [ ] JWT secret (`JWT_SECRET`) is at least 32 characters of entropy
- [ ] `ADMIN_API_KEY`, `OPERATOR_API_KEY`, `ANALYST_API_KEY` are set to distinct high-entropy values
- [ ] CORS `allow_methods` is `["GET", "POST", "PUT", "DELETE"]` — not `["*"]`
- [ ] CORS `allow_headers` is an explicit whitelist — not `["*"]`
- [ ] Audit logs are written to a persistent volume (not lost on container restart)
- [ ] All API keys are rotated from any default or test values used during development

---

## 3. Observability

- [ ] `GET /api/v1/health/connectors` returns HTTP 200 with connector list
- [ ] `GET /api/v1/health/metrics` returns HTTP 200 with metric counters/histograms
- [ ] `GET /api/v1/health/sources` returns HTTP 200 with source health dashboard
- [ ] `GET /healthz` and `GET /readyz` return HTTP 200
- [ ] Prometheus scrape (`GET /metrics`) returns metric data (requires `prometheus-fastapi-instrumentator` installed)
- [ ] Alerting rules from `docs/ALERTING_RULES.md` are loaded into the Prometheus instance
- [ ] On-call runbook (`docs/RUNBOOK.md`) is accessible to the on-call engineer
- [ ] Disaster recovery playbook (`docs/DISASTER_RECOVERY.md`) has been reviewed by at least one engineer
- [ ] Alert notifications are routed to the correct PagerDuty / Slack channel
- [ ] Log shipping (structured JSON via `LOG_FORMAT=json`) is configured to the central log platform

---

## 4. Performance

- [ ] Replay query (`POST /api/v1/playback/query`) returns within 3 seconds for a 7-day window over the demo dataset
- [ ] Export job (`POST /api/v1/exports`) completes within 10 seconds for a 1000-event dataset
- [ ] `GET /api/v1/investigations` returns within 500 ms for ≤1000 investigations
- [ ] Rate limiting is active: `POST /api/analyze` returns HTTP 429 after 5 requests per minute
- [ ] `GET /api/v1/health/connectors` returns within 200 ms (connector health must never block a request)
- [ ] Background health prober (5-minute cycle) is running and populating connector records
- [ ] Redis (if configured): cache hit rate > 60% under normal load
- [ ] No synchronous blocking I/O (e.g. `http.get()` in a FastAPI route without `await`) in any hot path

---

## 5. Documentation

- [ ] `docs/ARCHITECTURE.md` version header reads 6.0.0 and date 2026-04-04
- [ ] `docs/API.md` includes a complete route table covering all registered routers from `app/main.py`
- [ ] `README.md` Quick Start steps produce a working app in < 5 minutes on a clean machine
- [ ] `docs/DEPLOYMENT.md` environment variable table matches `.env.example` — no undocumented required vars
- [ ] `docs/RUNBOOK.md` references the correct health endpoint URLs (verify against `app/main.py` route prefixes)
- [ ] `docs/ALERTING_RULES.md` alert thresholds have been reviewed and are not default placeholder values
- [ ] `docs/DATA_RETENTION_POLICY.md` reflects current source families and their retention windows
- [ ] `docs/ONCALL.md` escalation contacts are current
- [ ] `HANDOVER.md` Phase 6 section present and accurate

---

## 6. Deployment

- [ ] `docker compose up --build` completes without errors on a clean machine
- [ ] Docker image runs as non-root `appuser` (`docker compose exec api whoami` returns `appuser`)
- [ ] All required environment variables are documented in `.env.example`
- [ ] `APP_MODE` is explicitly set to `staging` or `production` in the production `.env` (not left as default)
- [ ] Database migrations: if `DATABASE_URL` is set, `alembic upgrade head` completes without errors
- [ ] Rollback procedure: `docker compose down && git checkout <previous-tag> && docker compose up --build` has been tested
- [ ] Docker image tag follows `argus-intel:<git-sha>` convention and matches the deployed commit
- [ ] Health check passes after a fresh container start: `curl http://localhost:8000/healthz` → `200`
- [ ] Log output appears in structured JSON format (`LOG_FORMAT=json`)
- [ ] Celery worker starts and connects to Redis (verify `docker compose logs worker` for `Connected to redis://`)

---

## Sign-off

| Role | Name | Date | Notes |
|---|---|---|---|
| Release engineer | | | |
| Security reviewer | | | |
| Operations lead | | | |

**Release approved:** ☐  
**Release blocked:** ☐ — _list blocking items here_
