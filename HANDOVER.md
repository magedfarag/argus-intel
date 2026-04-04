# Construction Activity Monitor — Project Handover

**Date:** 2026-03-28
**Repository:** https://github.com/magedfarag/argus-intel
**Branch:** `main`
**Test status:** 38 / 38 passing

---

## 1. Executive Summary

The project has been fully transformed from a static demo application into a
production-ready FastAPI service capable of:

- Accepting AOI geometry from an interactive Leaflet map
- Searching real satellite imagery (Sentinel-2 via Copernicus STAC; Landsat via USGS STAC)
- Running a rasterio NDVI change-detection pipeline on COG assets streamed over HTTPS
- Falling back to deterministic demo data when live credentials are absent
- Executing large-area analyses asynchronously via Celery + Redis
- Exposing a complete REST API (13 endpoints) with Pydantic v2 validation

All production code is committed to GitHub. The application runs in Docker Compose with
three services: `redis`, `api`, `worker`.

---

## 2. Repository Layout

```
argus-intel/
├── backend/app/
│   ├── main.py                   FastAPI app + lifespan DI wiring
│   ├── config.py                 Flat AppSettings (pydantic-settings)
│   ├── dependencies.py           FastAPI DI singletons
│   ├── logging_config.py         Structured JSON / text logging
│   ├── providers/
│   │   ├── base.py               SatelliteProvider ABC + ProviderUnavailableError
│   │   ├── demo.py               Always-available deterministic fallback (3 scenarios)
│   │   ├── sentinel2.py          Copernicus Data Space OAuth2 + STAC search
│   │   ├── landsat.py            USGS LandsatLook STAC (no auth required)
│   │   └── registry.py           Priority-ordered provider resolution
│   ├── services/
│   │   ├── analysis.py           Orchestrator: search → select → detect → fallback chain
│   │   ├── change_detection.py   Rasterio NDVI pipeline on remote COGs
│   │   ├── scene_selection.py    Composite ranking + before/after pair selection
│   │   └── job_manager.py        Redis-backed async job CRUD (in-memory fallback)
│   ├── cache/client.py           Redis primary + cachetools TTLCache fallback
│   ├── resilience/
│   │   ├── circuit_breaker.py    Thread-safe CLOSED / OPEN / HALF-OPEN per provider
│   │   └── retry.py              tenacity wait_random_exponential decorator
│   ├── models/
│   │   ├── requests.py           AnalyzeRequest, SearchRequest (Pydantic v2)
│   │   ├── responses.py          AnalyzeResponse, ChangeRecord, JobStatusResponse …
│   │   ├── scene.py              SceneMetadata dataclass
│   │   └── jobs.py               Job, JobState enum
│   ├── routers/                  7 routers — 13 total endpoints
│   ├── workers/
│   │   ├── celery_app.py         Celery instance (graceful no-op if Redis absent)
│   │   └── tasks.py              run_analysis_task Celery task
│   └── static/
│       ├── index.html            Map + controls + results UI
│       ├── app.js                Provider strip, mode badge, job polling, warnings
│       └── styles.css            Dark theme + all new component styles
├── tests/
│   ├── conftest.py               Session-scoped shared fixtures
│   ├── unit/                     27 tests (config, cache, demo provider, scene selection)
│   └── integration/test_api.py  11 tests — all endpoints tested
├── docs/
│   ├── API.md                    Legacy endpoint reference (needs refresh — see §8)
│   ├── ARCHITECTURE.md           Legacy architecture notes (needs refresh — see §8)
│   ├── DEPLOYMENT.md             NEW — Docker + env vars operational guide
│   ├── PROVIDERS.md              NEW — Sentinel-2 / Landsat credential setup
│   └── CHANGE_DETECTION.md      NEW — Pipeline technical reference
├── .env.example                  All 22 env vars documented with defaults
├── docker-compose.yml            redis + api + worker services
├── Dockerfile                    Multi-stage build; libgdal in both stages
├── requirements.txt              All runtime deps pinned
└── requirements-dev.txt          pytest, httpx, pytest-cov
```

---

## 3. Architecture

### Synchronous request lifecycle

```
Browser  POST /api/analyze
  │
  ▼
analyze.py router — Pydantic validation, area bounds check
  │   large AOI (> ASYNC_AREA_THRESHOLD_KM2) → promote to async
  ▼
AnalysisService.run_sync()
  │
  ├─ Cache lookup (Redis or TTLCache)        ──hit──▶ return cached AnalyzeResponse
  │
  ├─ ProviderRegistry.select_provider()
  │     priority: sentinel2 → landsat → demo
  │
  ├─ CircuitBreaker.is_open(provider)?       ──open──▶ skip, try next provider
  │
  ├─ provider.search_imagery()  ──tenacity retry──▶
  │     success: CircuitBreaker.record_success()
  │     failure: CircuitBreaker.record_failure()  →  try next provider
  │
  ├─ rank_scenes()   weighted score (cloud×0.40 + recency×0.35 + overlap×0.25)
  ├─ select_scene_pair()   (before, after) with ≥7-day temporal gap
  │
  ├─ run_change_detection()   rasterio COG streaming → NDVI → morphological filter
  │     graceful fallback: empty list + warning when rasterio unavailable
  │
  ├─ Cache write
  └─▶ AnalyzeResponse  {analysis_id, is_demo, changes[], stats, warnings[]}
```

### Async request lifecycle

```
Browser  POST /api/analyze  {async_execution: true}
           OR  area_km2 > ASYNC_AREA_THRESHOLD_KM2 (default 25)
  │
  ▼
JobManager.create_job()  +  Celery task enqueued
  └─▶ immediate 202  {job_id: "…"}

Browser polls  GET /api/jobs/{job_id}  every 3 s
  └─ state == "completed"  →  renderAnalysisResult(job.result)
  └─ state == "failed"     →  show error

Celery worker:
  run_analysis_task()  →  AnalysisService.run_sync()
  JobManager.update_job(state=completed, result=…)
```

### Provider fallback chain

```
requested provider
  → CircuitBreaker OPEN or ProviderUnavailableError
  → try next registered provider (priority order)
  → all live providers failed → DemoProvider()
     AnalyzeResponse.is_demo = True
     AnalyzeResponse.warnings += ["Falling back to demo data — …"]
```

---

## 4. Key Technical Decisions

| Decision | Rationale |
|---|---|
| Flat `AppSettings` model | Nested `BaseSettings` owned by a parent don't inherit `env_file` → silent `.env` misses |
| Per-provider `CircuitBreaker` | One failing STAC endpoint doesn't block every request |
| `tenacity wait_random_exponential` | Jitter prevents thundering-herd on rate-limited endpoints |
| rasterio native HTTPS (COG) | No asset staging required; only the AOI window is read |
| Redis + TTLCache dual-layer cache | Zero-config local dev; upgrades automatically when Redis is present |
| `DemoProvider` always registered | Guarantees the app always returns a response, regardless of credentials |
| `from __future__ import annotations` | Deferred evaluation on all modules; forward references work without quoting |
| Non-root `appuser` in Dockerfile | OWASP A05 — principle of least privilege |

---

## 5. Completed Work

### Phase 1 — Production transformation (36 Python modules)
- [x] Flat `AppSettings` with `pydantic-settings`; full `.env` support
- [x] `Sentinel2Provider` — OAuth2 client_credentials + Copernicus STAC search
- [x] `LandsatProvider` — USGS LandsatLook STAC (public, no auth)
- [x] `DemoProvider` — deterministic fallback; 3 curated construction scenarios
- [x] `ProviderRegistry` — priority-ordered resolution + credential validation
- [x] `AnalysisService` — full fallback chain, cache integration, circuit breaker
- [x] `ChangeDetectionService` — rasterio NDVI pipeline on remote COGs
- [x] `SceneSelectionService` — composite quality ranking + before/after pair
- [x] `JobManager` — Redis + in-memory async job store
- [x] `CacheClient` — Redis primary + cachetools `TTLCache` fallback
- [x] `CircuitBreaker` — thread-safe CLOSED/OPEN/HALF-OPEN per provider
- [x] Retry decorator — `tenacity wait_random_exponential`
- [x] 7 FastAPI routers (13 total endpoints)
- [x] Celery worker + graceful no-op when Redis absent
- [x] Multi-stage Dockerfile (libgdal, non-root `appuser`)
- [x] `docker-compose.yml` (redis + api + worker)
- [x] `.env.example` — 22 variables documented

### Phase 2 — Git + GitHub
- [x] `.gitignore` created
- [x] Initial commit: 102 files, 16 260 insertions
- [x] GitHub repository created: https://github.com/magedfarag/argus-intel
- [x] Default branch: `main`

### Phase 3 — Quality
- [x] `tests/conftest.py` — session-scoped shared fixtures
- [x] `CircuitBreaker` wired into `AnalysisService._run_live_analysis()`
- [x] `analyze.py` router injects `breaker` from DI
- [x] `providers.py` duplicate-code bug fixed
- [x] **38 / 38 tests passing**

### Phase 4 — Frontend
- [x] `index.html` — provider strip, mode badge, cloud slider, processing mode,
      async toggle, job-progress section, warning banner
- [x] `app.js` — `loadProviders()`, `loadConfig()`, async job polling (3 s),
      `showWarnings()`, demo badge, confidence pill colours, per-change warnings
- [x] `styles.css` — provider chips, badge variants, pill variants, spinner,
      warning banner, `.hidden` utility class

### Phase 5 — Documentation (this wave)
- [x] `HANDOVER.md` — this file
- [x] `docs/DEPLOYMENT.md` — operational deployment guide
- [x] `docs/PROVIDERS.md` — Sentinel-2 / Landsat credential setup
- [x] `docs/CHANGE_DETECTION.md` — pipeline technical reference
- [x] `README.md` — updated for production system

### WorldView Phase 5 — Investigation Workflows (2026-04-04) COMPLETE

All four backend tracks delivered and verified:

| Track | Service | Tests | Endpoints |
|-------|---------|-------|-----------|
| A — Saved Investigations | `src/services/investigation_service.py` | 47 (23 unit + 24 integration) | `/api/v1/investigations` (10 endpoints) |
| B — Evidence Packs | `src/services/evidence_pack_service.py` | 29 (15 unit + 14 integration) | `/api/v1/evidence-packs` (7 endpoints) |
| C — Analyst Workflows | `src/services/analyst_query_service.py` | 39 (20 unit + 19 integration) | `/api/v1/analyst` (11 endpoints) |
| D — Absence Analytics | `src/services/absence_analytics.py` | 45 (24 unit + 21 integration) | `/api/v1/absence` (8 endpoints) |

**Frontend**: `InvestigationsPanel` React component with investigation navigation and absence-alert surfaces; 14 frontend tests pass; TypeScript compiles with 0 errors.

**Suite totals**: 1338 backend tests passing (0 failures, 11 skipped); 14/14 frontend tests passing.

All four routers registered exactly once in `app/main.py`. No duplicate registrations. All Phase 5 exit criteria met. Milestone 5 marked COMPLETE in `docs/worldview-transformation-plan/MILESTONES.md`.

---

## 6. Pending Tasks

### P1 — Critical (blocks production use)

| ID | Task | Notes |
|---|---|---|
| P1-1 | Obtain Sentinel-2 credentials | Register at https://dataspace.copernicus.eu; set `SENTINEL2_CLIENT_ID` + `SENTINEL2_CLIENT_SECRET` |
| P1-2 | Provision Redis | `docker compose up redis` locally; managed Redis (e.g. Redis Cloud) for production |
| P1-3 | Validate rasterio on target host | Dockerfile installs `libgdal32`; confirm GDAL version matches the distribution's apt repo |
| P1-4 | Set `APP_MODE=live` in production `.env` | Surfaces errors when no live provider resolves instead of silently returning demo data |
| P1-5 | Restrict CORS `allow_origins` | Change `allow_origins=["*"]` in `main.py` to the specific frontend domain |
| P1-6 | Add authentication / API key middleware | No auth currently on any endpoint — must be secured before exposing to the internet |

### P2 — Important

| ID | Task | Notes |
|---|---|---|
| P2-1 | Add pytest-cov and 80 % threshold to CI | `pytest --cov=backend/app --cov-fail-under=80` |
| P2-2 | Test circuit breaker state transitions | Unit test: CLOSED→OPEN after N failures; OPEN→HALF-OPEN after timeout |
| P2-3 | Test async job dispatch + poll cycle | Integration test: `async_execution=True` → `job_id` → poll until `completed` |
| P2-4 | GitHub Actions CI workflow | `.github/workflows/ci.yml` — pytest + ruff + Docker build on every push |
| P2-5 | Rate-limit `/api/analyze` | Add `slowapi` or CDN-level rate limiting |

### P3 — Nice to have

| ID | Task | Notes |
|---|---|---|
| P3-1 | Commercial provider stub | `MaxarProvider` or `PlanetProvider` extending `SatelliteProvider` |
| P3-2 | WebSocket live progress | Replace 3 s polling with `ws://…/api/jobs/{id}/stream` |
| P3-3 | Persist job history to PostgreSQL | Replace in-memory `JobManager` fallback with SQLAlchemy + pg |
| P3-4 | Multi-worker circuit breaker | Move `CircuitBreaker` state from process memory to Redis |
| P3-5 | Actual satellite thumbnails | Generate real scene thumbnails instead of static demo PNGs |
| P3-6 | `add_rate_limit` middleware | Protect all mutation endpoints |
| P3-7 | Refresh `docs/API.md` | Still references `demo-fusion` provider name from original demo |
| P3-8 | Refresh `docs/ARCHITECTURE.md` | Still describes demo-only architecture |

---

## 7. API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves `index.html` |
| GET | `/api/health` | Service status, mode, Redis state, provider states |
| GET | `/api/config` | Today, area bounds, default cloud threshold, provider list |
| GET | `/api/providers` | Availability + reason for each registered provider |
| GET | `/api/credits` | Data source attribution |
| POST | `/api/analyze` | Run change detection; returns result or `{job_id}` |
| GET | `/api/jobs/{id}` | Job state + result when complete (requires Redis) |
| DELETE | `/api/jobs/{id}` | Cancel / delete a job (requires Redis) |
| POST | `/api/search` | Search imagery without running detection |

### POST /api/analyze — request body

```json
{
  "geometry":        { "type": "Polygon", "coordinates": [[…]] },
  "start_date":      "2026-02-26",
  "end_date":        "2026-03-28",
  "provider":        "auto",
  "area_km2":        19.857,
  "cloud_threshold": 20.0,
  "processing_mode": "balanced",
  "async_execution": false
}
```

`provider`: `auto` | `demo` | `sentinel2` | `landsat`
`processing_mode`: `fast` | `balanced` | `thorough`

---

## 8. Configuration Reference

See `.env.example` for the full annotated list. Key variables:

| Variable | Default | Required for |
|---|---|---|
| `APP_MODE` | `auto` | Mode (`demo` / `auto` / `live`) |
| `SENTINEL2_CLIENT_ID` | `` | Live Sentinel-2 imagery |
| `SENTINEL2_CLIENT_SECRET` | `` | Live Sentinel-2 imagery |
| `REDIS_URL` | `` | Async jobs + distributed cache |
| `DEFAULT_CLOUD_THRESHOLD` | `20` | Analysis default |
| `ASYNC_AREA_THRESHOLD_KM2` | `25` | Auto-async promotion |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Resilience |

---

## 9. Running the Application

### Local dev — no Redis (demo mode)

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://127.0.0.1:8000
```

### Local with Redis + Celery worker

```powershell
docker run -p 6379:6379 redis:7-alpine             # Terminal 1

$env:REDIS_URL = "redis://localhost:6379/0"
uvicorn app.main:app --reload               # Terminal 2

$env:REDIS_URL = "redis://localhost:6379/0"
celery -A app.workers.celery_app.celery_app worker --loglevel=info --pool=solo  # Terminal 3
```

### Docker Compose (full stack)

```bash
cp .env.example .env   # then fill in credentials
docker compose up --build
# http://localhost:8000
```

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

---

## 10. Known Limitations

| # | Limitation | Severity |
|---|---|---|
| L1 | Change detection returns empty list if rasterio unavailable | High — Dockerfile handles this |
| L2 | `CircuitBreaker` state is per-process (not shared across workers) | Medium |
| L3 | Flat-earth area approximation in `_polygon_area_km2()` | Low |
| L4 | No authentication / authorization on any endpoint | **Critical** — must fix before production |
| L5 | CORS `allow_origins=["*"]` | High — restrict in production |
| L6 | Async job result expires after 24 h (Redis TTL) | Low |
| L7 | No rate limiting on `/api/analyze` | High |
| L8 | `docs/API.md` and `docs/ARCHITECTURE.md` reflect old demo only | Low |

---

## 11. Security Checklist (OWASP Top 10)

| Risk | Status |
|---|---|
| A01 Broken Access Control | **OPEN** — no auth (P1-6) |
| A02 Cryptographic Failures | ✅ Credentials in env vars; `.env` in `.gitignore` |
| A03 Injection | ✅ Pydantic validation; parameterised STAC queries |
| A05 Security Misconfiguration | ⚠️ CORS `*` must be tightened (P1-5) |
| A06 Vulnerable Components | ⚠️ Run `pip-audit` periodically |
| A07 Auth / Identification | **OPEN** — add API key middleware (P1-6) |

---

## 12. Resources

| Resource | URL |
|---|---|
| GitHub repository | https://github.com/magedfarag/argus-intel |
| Copernicus CDSE registration | https://dataspace.copernicus.eu |
| Copernicus STAC API | https://catalogue.dataspace.copernicus.eu/stac/v1 |
| USGS LandsatLook STAC | https://landsatlook.usgs.gov/stac-server |
| FastAPI Swagger UI (local) | http://localhost:8000/docs |

---

## 13. Phase 0 Stabilization — Status (2026-04-04)

**Verdict:** PHASE 0 SUBSTANTIALLY COMPLETE — one deferred item (globe vitest smoke test blocked by missing vitest install)

### What was fixed

| Area | Fix |
|---|---|
| `app/workers/tasks.py` | Annotated 4 demo-only ingestion shortcuts: GDELT, OpenSky, and AISStream pollers normalize events but discard them (no EventStore write); `enforce_telemetry_retention` operates on in-memory store only |
| `app/workers/tasks.py` | `TelemetryStore.upsert()` → `ingest_batch()` interface mismatch corrected in `poll_rapidapi_ais` and `poll_vessel_data` |
| `tests/unit/test_cache.py` | Cache test design contract aligned with the real `CacheClient` interface |
| `.github/workflows/ci.yml` | Frontend `typecheck` job added; catches Globe/API-contract type regressions in CI |
| `frontend/src/components/GlobeView/GlobeView.tsx` | Fixed `bbox`/`geometry` contract, `last_known_position` → `last_known_lon`/`last_known_lat` split, removed unused `baseStyle` prop |

### What is deferred to Phase 1

| Item | Phase 1 Track |
|---|---|
| GDELT / OpenSky / AISStream pollers → EventStore unified write path | Track C |
| EventStore / TelemetryStore schema and contract freeze | Track A |
| Globe vitest smoke test (blocked: vitest not yet installed) | Track A |

### Baseline health (2026-04-04)

- **Unit tests:** 856 passing, 0 failing
- **Frontend typecheck:** `tsc --noEmit` exits clean
- **CI:** typecheck + backend unit tests gated on every push

---

## 14. Phase 6 — Hardening and Release (2026-04-04)

**Status:** COMPLETE — all four tracks delivered.

### Track A — Auth and Governance

| Deliverable | Location |
|---|---|
| HMAC-SHA256 token auth, 3-tier RBAC | `app/dependencies.py` |
| `AuditLoggingMiddleware` (zero request-path latency) | `app/audit_log.py` |
| 28 unit tests for auth (tamper detection, role hierarchy, bypass modes) | `tests/unit/test_auth_rbac.py` |
| 22 integration tests for auth gates and audit fields | `tests/integration/test_auth_audit.py` |
| Data retention policy by source family | `docs/DATA_RETENTION_POLICY.md` |

### Track B — Performance and Cost Controls

Track B (rate limiting, caching, budgets) was pre-implemented during earlier phases:
- `app/resilience/rate_limiter.py` — slowapi integration (5/10/20 req/min per endpoint)
- `app/cache/client.py` — Redis primary + TTLCache fallback
- In-process circuit breaker per provider

### Track C — Observability and Reliability

| Deliverable | Location |
|---|---|
| In-process metrics registry (counters, histograms, gauges) | `app/metrics.py` |
| Connector health endpoint | `GET /api/v1/health/connectors` |
| Metrics snapshot endpoint | `GET /api/v1/health/metrics` |
| 8 Prometheus alerting rules | `docs/ALERTING_RULES.md` |
| 6 incident response runbooks | `docs/RUNBOOK.md` §7 |
| Disaster recovery documentation | `docs/DISASTER_RECOVERY.md` |

### Track D — Release Readiness (this wave)

| Deliverable | Location |
|---|---|
| Refreshed `docs/ARCHITECTURE.md` (v6.0) | `docs/ARCHITECTURE.md` |
| Complete API route table (85+ endpoints) | `docs/API.md` |
| Updated `README.md` (current feature set, auth, docs index) | `README.md` |
| Release checklist (6 categories, manual-verify format) | `docs/RELEASE_CHECKLIST.md` |
| Deployment candidate notes (limitations, next steps) | `docs/DEPLOYMENT_CANDIDATE.md` |
| Final regression pass: 1428 passed, 11 skipped, 0 failed | — |
| Frontend typecheck: clean (0 errors) | — |

### Current test count

| Scope | Count |
|---|---|
| Backend tests passing | 1428 |
| Backend tests skipped (pre-existing: Celery/Redis CI, sentinel2/thumbnails) | 11 |
| Backend tests failing | 0 |
| Frontend tests | 14 (all passing, as of Milestone 5) |

### Known limitations (before production use)

| # | Limitation | Severity |
|---|---|---|
| L1 | All V2 stores are in-memory — no persistence across restarts | Critical |
| L2 | Auth uses HMAC self-signed tokens — no external IdP | High |
| L3 | All connectors are stubs — no live external API calls activated by default | High |
| L4 | Rate limiting is per-worker in-process — no Redis coordination for multi-worker | Medium |
| L5 | 3D scene orbit paths use flat-earth approximations — not WGS-84 accurate | Low |
| L6 | Audit `user_id` is SHA-256 prefix — no central identity mapping | Low |

### Recommended next steps

1. **Postgres persistence**: Wire `EventStore`, `InvestigationService`, `AbsenceAnalyticsService` to PostGIS (Alembic migrations present in `alembic/`)
2. **Redis caching**: Replace per-worker rate limiter and circuit breaker state with shared Redis
3. **External identity provider**: Replace HMAC tokens with OAuth2 / OIDC (e.g. Keycloak, Auth0)
4. **Live connector activation**: Provide `AISSTREAM_API_KEY`, `OPENSKY_USERNAME`/`PASSWORD`, Sentinel-2/Landsat credentials
5. **WGS-84 orbit paths**: Replace flat-earth TLE approximation in `src/api/orbits.py`
6. **CI coverage gate**: Add `pytest --cov=app --cov-fail-under=85` to `.github/workflows/ci.yml`
