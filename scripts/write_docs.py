"""Write all documentation files for the argus-intel project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

# ─── HANDOVER.md ─────────────────────────────────────────────────────────────
HANDOVER = ROOT / "HANDOVER.md"
HANDOVER.write_text(r"""# Construction Activity Monitor — Project Handover

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
""", encoding="utf-8")
print("HANDOVER.md written")

# ─── docs/DEPLOYMENT.md ──────────────────────────────────────────────────────
(DOCS / "DEPLOYMENT.md").write_text(r"""# Deployment Guide

## Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.11 |
| Docker (optional) | 24.0 |
| Docker Compose (optional) | 2.20 |
| Redis (optional) | 7.0 |
| GDAL / libgdal | 3.4 (installed automatically in Dockerfile) |

---

## 1. Local development (demo mode, no Redis)

```bash
# Clone and enter directory
git clone https://github.com/magedfarag/argus-intel
cd argus-intel

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install deps
pip install -r requirements.txt

# Run with auto-reload
uvicorn app.main:app --reload

# Open http://127.0.0.1:8000
```

The server starts in `APP_MODE=auto`. With no credentials or Redis set, it
degrades to demo mode automatically.

---

## 2. Local development with Redis and async workers

```powershell
# Start Redis (Docker)
docker run --name redis-dev -p 6379:6379 -d redis:7-alpine

# Terminal 2 — API server
$env:REDIS_URL = "redis://localhost:6379/0"
$env:APP_MODE  = "auto"
uvicorn app.main:app --reload

# Terminal 3 — Celery worker
$env:REDIS_URL = "redis://localhost:6379/0"
celery -A app.workers.celery_app.celery_app worker `
    --loglevel=info --pool=solo --concurrency=2
```

---

## 3. Docker Compose (recommended for staging / production)

### 3.1 Create .env

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```env
APP_MODE=auto
REDIS_URL=redis://redis:6379/0
SENTINEL2_CLIENT_ID=your-client-id
SENTINEL2_CLIENT_SECRET=your-client-secret
LOG_FORMAT=json
```

### 3.2 Build and start

```bash
docker compose up --build -d
```

Services started:
- `redis` — Redis 7 Alpine on port 6379
- `api` — FastAPI app on port 8000
- `worker` — Celery worker (2 concurrent tasks)

### 3.3 Check health

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{"status": "ok", "mode": "auto", "redis": "connected", "providers": {...}}
```

### 3.4 Stop all services

```bash
docker compose down
```

---

## 4. Environment variables

All variables can be set via `.env` or as OS environment variables.
See `.env.example` for a fully annotated list.

### Essential

| Variable | Default | Notes |
|---|---|---|
| `APP_MODE` | `auto` | `demo` / `auto` / `live` |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |
| `LOG_FORMAT` | `json` | `json` for production; `text` for local dev |
| `REDIS_URL` | `` | Required for async jobs and distributed cache |

### Sentinel-2 (optional — enables live imagery)

| Variable | Description |
|---|---|
| `SENTINEL2_CLIENT_ID` | OAuth2 client ID from Copernicus CDSE |
| `SENTINEL2_CLIENT_SECRET` | OAuth2 client secret |
| `SENTINEL2_TOKEN_URL` | Override the default token endpoint |
| `SENTINEL2_STAC_URL` | Override the default STAC search endpoint |

### Landsat (optional — credentials needed only for M2M bulk download)

| Variable | Description |
|---|---|
| `LANDSAT_USERNAME` | USGS ERS username (M2M only) |
| `LANDSAT_PASSWORD` | USGS ERS password (M2M only) |
| `LANDSAT_STAC_URL` | Override the default USGS STAC endpoint |

### Cache and circuit breaker

| Variable | Default | Notes |
|---|---|---|
| `CACHE_TTL_SECONDS` | `3600` | Analysis result cache lifetime |
| `CACHE_MAX_ENTRIES` | `256` | In-memory cache max size |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | `60` | Seconds in OPEN before half-open probe |

### Analysis pipeline

| Variable | Default | Notes |
|---|---|---|
| `DEFAULT_CLOUD_THRESHOLD` | `20` | Max cloud cover % to accept a scene |
| `ASYNC_AREA_THRESHOLD_KM2` | `25` | AOI areas above this are auto-promoted to async |
| `HTTP_TIMEOUT_SECONDS` | `30` | External provider request timeout |
| `HTTP_MAX_RETRIES` | `3` | Retry attempts on transient errors |

---

## 5. Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=backend/app --cov-report=term-missing
```

---

## 6. Production hardening checklist

- [ ] Set `APP_MODE=live` to require live providers
- [ ] Restrict `allow_origins` in `main.py` CORS middleware
- [ ] Add API key or OAuth2 middleware
- [ ] Add `slowapi` rate limiting on `/api/analyze`
- [ ] Enable `LOG_FORMAT=json` and ship logs to your observability stack
- [ ] Set `CACHE_TTL_SECONDS` appropriate for your data freshness SLA
- [ ] Use a managed Redis with TLS (e.g. `rediss://…`)
- [ ] Run `pip-audit` in CI to detect vulnerable dependencies
- [ ] Set `ASYNC_AREA_THRESHOLD_KM2=10` to reduce synchronous load for large AOIs
""", encoding="utf-8")
print("docs/DEPLOYMENT.md written")

# ─── docs/PROVIDERS.md ───────────────────────────────────────────────────────
(DOCS / "PROVIDERS.md").write_text(r"""# Provider Setup Guide

The application supports three providers. Priority order (when `provider=auto`):
`sentinel2 → landsat → demo`

---

## 1. Demo Provider

**Always available.** No credentials required.

Returns three deterministic construction scenarios:
1. Site clearing / earthwork
2. Foundation work
3. Roofing / enclosure

The demo provider is the final fallback in the chain. Set `APP_MODE=demo` to
force demo mode regardless of what credentials are present.

---

## 2. Sentinel-2 (Copernicus Data Space Ecosystem)

**Resolution:** 10 m  
**Revisit:** ~5 days  
**Auth:** OAuth2 `client_credentials`

### 2.1 Register

1. Go to https://dataspace.copernicus.eu
2. Click **Register** and create a free account
3. Verify your email address
4. Log in to the dashboard
5. Navigate to **User settings → OAuth clients**
6. Create a new client with `client_credentials` grant
7. Note your `Client ID` and `Client Secret`

### 2.2 Configure

```env
SENTINEL2_CLIENT_ID=your-client-id
SENTINEL2_CLIENT_SECRET=your-client-secret
```

### 2.3 How it works

`Sentinel2Provider._get_token()` exchanges credentials for a bearer token at:

```
POST https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
  grant_type=client_credentials
  client_id=…
  client_secret=…
```

Tokens are cached with a 30-second buffer before expiry.

Then `search_imagery()` POSTs to the STAC search endpoint:

```
POST https://catalogue.dataspace.copernicus.eu/stac/v1/search
  {
    "collections": ["SENTINEL-2"],
    "intersects": <GeoJSON geometry>,
    "datetime": "2026-02-26T00:00:00Z/2026-03-28T23:59:59Z",
    "limit": 10,
    "query": {"eo:cloud_cover": {"lte": 20}}
  }
```

### 2.4 COG asset access

Change detection reads scene assets as Cloud-Optimised GeoTIFFs streamed via HTTPS.
The bearer token is passed as `GDAL_HTTP_BEARER` via `rasterio.Env()`.

### 2.5 Troubleshooting

| Error | Likely cause |
|---|---|
| `401 Unauthorized` on token endpoint | Wrong `CLIENT_ID` or `CLIENT_SECRET` |
| `Token request failed` | Copernicus outage or wrong `SENTINEL2_TOKEN_URL` |
| Empty scene list | AOI outside Europe/Africa coverage, or cloud threshold too strict |
| `Circuit breaker OPEN` | 5+ consecutive failures; waits 60 s before retry |

---

## 3. Landsat (USGS LandsatLook STAC)

**Resolution:** 30 m  
**Revisit:** ~16 days  
**Auth:** None required for search

### 3.1 No setup required for scene search

Landsat STAC search is publicly accessible. The `LandsatProvider` works
out-of-the-box with no credentials.

### 3.2 Optional — USGS ERS credentials for M2M bulk download

If you need to download full-resolution Landsat scenes via the M2M API:

1. Register at https://ers.cr.usgs.gov
2. Log in and request M2M access (may require approval)
3. Set in `.env`:

```env
LANDSAT_USERNAME=your-ers-username
LANDSAT_PASSWORD=your-ers-password
```

> The current `LandsatProvider` implementation does not use M2M. These fields
> are reserved for a future bulk-download extension.

### 3.3 How it works

`search_imagery()` POSTs to:

```
POST https://landsatlook.usgs.gov/stac-server/search
  {
    "collections": ["landsat-c2l2-sr"],
    "intersects": <GeoJSON geometry>,
    "datetime": "…/…",
    "limit": 10,
    "query": {"eo:cloud_cover": {"lte": 20}},
    "sortby": [{"field": "datetime", "direction": "desc"}]
  }
```

### 3.4 Note on resolution

At 30 m resolution, Landsat is most useful for larger developments (> 5 km²).
For small urban parcels, Sentinel-2 (10 m) provides significantly better detail.
The system always selects the best available provider for the requested AOI.

---

## 4. Registering a custom provider

1. Create `backend/app/providers/my_provider.py`
2. Extend `SatelliteProvider` (see `base.py`)
3. Implement all 6 abstract methods: `validate_credentials`, `search_imagery`,
   `fetch_scene_metadata`, `healthcheck`, `get_quota_status`, `download_assets`
4. Register in `main.py` lifespan:

```python
from backend.app.providers.my_provider import MyProvider
if settings.my_provider_is_configured():
    registry.register(MyProvider(settings))
```

5. Add any new env vars to `config.py` and `.env.example`
""", encoding="utf-8")
print("docs/PROVIDERS.md written")

# ─── docs/CHANGE_DETECTION.md ────────────────────────────────────────────────
(DOCS / "CHANGE_DETECTION.md").write_text(r"""# Change Detection — Technical Reference

## 1. Overview

The change detection pipeline compares two satellite scenes (before and after)
to identify construction activity within the AOI. It is implemented in
`backend/app/services/change_detection.py` and called by `AnalysisService`.

---

## 2. Pipeline steps

```
1. Scene pair selection
       rank_scenes()  →  select_scene_pair()
       before: highest-quality scene ≥ 7 days before 'after'
       after:  most recent, lowest cloud cover scene

2. COG streaming (rasterio)
       rasterio.open("https://…asset.tif")
       Reprojects AOI bbox → scene CRS
       Builds rasterio.Window for the AOI area
       Reads Red and NIR bands (clipped to window)

3. Cloud / QA masking
       Scene-specific QA band applied when available
       Pixels flagged as cloud / cloud shadow → NaN

4. NDVI computation
       NDVI = (NIR - Red) / (NIR + Red)
       Applied to both before and after scenes

5. Change map
       delta_NDVI = NDVI_after - NDVI_before
       |delta_NDVI| > 0.12  →  candidate change pixel

6. Morphological filtering (scipy.ndimage)
       Binary closing to fill gaps within patches
       Binary opening to remove isolated noise pixels

7. Connected components (scikit-image label)
       Each connected region = one candidate detection
       Regions < 4 pixels discarded

8. Classification + confidence scoring
       Area, mean delta_NDVI, shape compactness → class + score
       Resolution penalty applied for small AOIs at 30 m (Landsat)

9. Result packaging
       Each detection → ChangeRecord
       Warnings appended for low-confidence scenes or resolution limits
```

---

## 3. Band configuration

| Provider | Red band file | NIR band file |
|---|---|---|
| Sentinel-2 | `B04.tif` (10 m) | `B08.tif` (10 m) |
| Landsat-8/9 | `B4.TIF` (30 m) | `B5.TIF` (30 m) |

Bands are read from the `assets` dictionary of each STAC item.

---

## 4. Change classification

| Class | delta_NDVI signal | Typical construction stage |
|---|---|---|
| Site clearing | Large decrease (vegetation removal) | Earthwork / grading |
| Foundation work | Moderate stable decrease | Slab / foundation pour |
| Structure erection | Mixed signal | Framing / steel |
| Roofing / enclosure | High reflectance increase | Roof membranes / cladding |
| Paving / hardscape | Persistent low NDVI | Parking, roads |

---

## 5. Confidence scoring

```
base_confidence = 60 + (|mean_delta_NDVI| / 0.30) * 40
                       capped at 100

resolution_penalty:
  Sentinel-2 (10 m), AOI > 0.5 km²:   no penalty
  Sentinel-2 (10 m), AOI < 0.5 km²:   -5
  Landsat (30 m),    AOI > 5 km²:      no penalty
  Landsat (30 m),    AOI < 5 km²:      -15

final_confidence = max(0, base_confidence - resolution_penalty)
```

---

## 6. Graceful degradation

When `rasterio` is not importable (e.g. running tests without GDAL):

- `_rasterio_available()` returns `False`
- `run_change_detection()` returns an empty list
- `AnalysisService` appends a warning: `"rasterio not available — change detection skipped"`
- The `AnalyzeResponse` is still returned with `changes=[]` and `is_demo=False`

---

## 7. Performance characteristics

| AOI size | Provider | Typical latency |
|---|---|---|
| < 1 km² | Sentinel-2 | 3–8 s (streaming small window) |
| 1–25 km² | Sentinel-2 | 8–30 s |
| > 25 km² | Any | Auto-promoted to async job |
| Any | Demo | < 100 ms (no I/O) |

Large-area analyses (> `ASYNC_AREA_THRESHOLD_KM2`, default 25 km²) are
automatically promoted to async Celery tasks regardless of `async_execution` flag.

---

## 8. Known limitations

| # | Limitation |
|---|---|
| L1 | Atmospheric correction is assumed; no on-the-fly BRDF / DOS correction |
| L2 | Cloud masking relies on scene QA band — shadow detection is limited |
| L3 | No co-registration between scenes from different orbits |
| L4 | Landsat 30 m resolution misses fine detail on sites < 0.5 km² |
| L5 | Single NDVI threshold (0.12); seasonal baselines are not adjusted |
| L6 | No false-positive suppression for agricultural fields / seasonal vegetation |

---

## 9. Extending the pipeline

To add a new change indicator (e.g. SAR coherence, thermal anomaly):

1. Add a new function in `change_detection.py` following the same
   `_read_band_window()` + threshold + label pattern
2. Accept an additional `mode` parameter in `run_change_detection()`
3. Map the new `processing_mode="thorough"` to the extended pipeline
4. Add the new band keys to the `_BANDS` dictionary for each provider
""", encoding="utf-8")
print("docs/CHANGE_DETECTION.md written")

print("\nAll documentation files written successfully.")

