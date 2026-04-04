# ARGUS — Multi-Domain Surveillance Intelligence

A production release-candidate FastAPI + React platform for multi-domain surveillance:
ships, aircraft, satellites, GDELT events, signals intelligence, and analyst investigations.
AOI-based monitoring with 2D map and 3D globe views, full replay, sensor fusion, RBAC auth,
and audit logging. Falls back to curated demo data when live credentials are absent.

**Repository:** https://github.com/magedfarag/argus-intel  
**Tests:** 1428 passed, 11 skipped (2026-04-04)  
**Stack:** Python 3.11+ · FastAPI · Pydantic v2 · React + TypeScript · Vite · Celery + Redis · rasterio · MapLibre GL JS · deck.gl

---

## Quick start

### Demo mode (no credentials or Redis needed)

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# Open http://127.0.0.1:8000
```

In demo mode all auth role-checks are bypassed and the app seeds synthetic ship tracks,
flight tracks, GDELT events, imagery, and an AOI on first start.

### Full stack with Docker Compose

```bash
cp .env.example .env          # fill in credentials + REDIS_URL
docker compose up --build
# Open http://localhost:8000
```

---

## Authentication

The platform uses HMAC-SHA256 signed tokens with three roles: `analyst`, `operator`, `admin`.

| Mode | Auth behaviour |
|---|---|
| `APP_MODE=demo` | All auth checks bypassed; all requests treated as `admin` |
| `API_KEY` not set (dev) | All requests treated as `admin` |
| `API_KEY` set | Raw key match → `analyst` role |
| Tiered keys set | `ADMIN_API_KEY` / `OPERATOR_API_KEY` / `ANALYST_API_KEY` map to their roles |

```bash
# Use Bearer token
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/investigations

# Or API key header
curl -H "X-API-Key: <key>" http://localhost:8000/api/v1/investigations
```

See [docs/API.md](docs/API.md) for the full route table and auth requirements per endpoint.

---

## Features

| Phase | Feature | Detail |
|---|---|---|
| 0 | AOI selection | Polygon / rectangle / circle on MapLibre map; bounding-box entry |
| 0 | Area validation | 0.01–100 km² enforced client-side and server-side |
| 1 | Live Sentinel-2 | Copernicus CDSE STAC; OAuth2 bearer token |
| 1 | Live Landsat | USGS LandsatLook STAC; no credentials required for search |
| 1 | Demo fallback | Always-available synthetic data; automatic when live providers unavailable |
| 1 | NDVI change detection | rasterio pipeline on COG assets streamed via HTTPS |
| 1 | Async jobs | Celery + Redis for large AOIs (>25 km²); WebSocket + HTTP polling |
| 1 | Caching | Redis primary + in-process TTLCache fallback |
| 1 | Circuit breaker | Per-provider CLOSED / OPEN / HALF-OPEN state machine |
| 2 | Orbits | Satellite pass predictions (flat-earth TLE approximation) |
| 2 | Airspace | No-fly zones, violation alerts, NOTAM stream |
| 2 | Jamming | GPS/GNSS jamming event detection and affected-arc queries |
| 2 | Strikes | Strike reconstruction with evidence attachment |
| 3 | 3D world | MapLibre GL JS + deck.gl; DEM terrain + hillshade + opt-in buildings |
| 3 | Scene performance | `useScenePerformance` hook + frame-budget overlay |
| 4 | Render modes | Thermal / night-vision / low-light CSS filter overlays |
| 4 | Camera feeds | `CameraFeedPanel` with observation highlighting and fly-to |
| 4 | Detection overlays | Confidence-radius circles; click popups on MapView and GlobeView |
| 5 | Investigations | Saved investigations with evidence, AOI linking, close/reopen lifecycle |
| 5 | Evidence packs | ZIP evidence export with narrative sections |
| 5 | Analyst queries | Saved queries, AI briefing generation |
| 5 | Absence analytics | Absence-as-signal; AIS gap scanning |
| 6 | RBAC auth | 3-tier roles (analyst/operator/admin) with HMAC-SHA256 tokens |
| 6 | Audit logging | Append-only JSON audit trail; zero request-path latency |
| 6 | Observability | In-process metrics, connector health dashboard, Prometheus endpoint |
| 6 | Alerting | 8 Prometheus alerting rules; 6 incident runbooks |

---

## Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
# Expected: 1428 passed, 11 skipped
```

Frontend typecheck:
```bash
cd frontend
npx tsc --noEmit
# Expected: no output (clean)
```

---

## Documentation

| Document | Purpose |
|---|---|
| [docs/API.md](docs/API.md) | Complete route table (all 85+ endpoints) with auth requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full system architecture including RBAC, metrics, V2 layers |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, env vars, production deployment steps |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Incident response runbooks (6 runbooks) |
| [docs/ALERTING_RULES.md](docs/ALERTING_RULES.md) | 8 Prometheus alerting rules |
| [docs/DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md) | DR assumptions and recovery procedures |
| [docs/DATA_RETENTION_POLICY.md](docs/DATA_RETENTION_POLICY.md) | Data retention by source family and governance |
| [docs/ONCALL.md](docs/ONCALL.md) | On-call handoff and quick diagnostics |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Sentinel-2 / Landsat credential setup |
| [docs/CHANGE_DETECTION.md](docs/CHANGE_DETECTION.md) | NDVI pipeline, scoring, limitations |
| [HANDOVER.md](HANDOVER.md) | Full project handover — phases, decisions, next steps |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | Release gate checklist (6 categories) |
| [docs/DEPLOYMENT_CANDIDATE.md](docs/DEPLOYMENT_CANDIDATE.md) | RC notes, known limitations, recommended next steps |



---

## Quick start

### Demo mode (no credentials or Redis needed)

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# Open http://127.0.0.1:8000
```

### Full stack with Docker Compose

```bash
cp .env.example .env          # fill in Sentinel-2 credentials + REDIS_URL
docker compose up --build
# Open http://localhost:8000
```

---

## Features

| Feature | Detail |
|---|---|
| AOI selection | Polygon / rectangle / circle drawn on Leaflet map, or enter bounding box |
| Area validation | 0.01 – 100 km² enforced client-side and server-side |
| Live Sentinel-2 | Copernicus Data Space STAC search; OAuth2 bearer token |
| Live Landsat | USGS LandsatLook STAC; no credentials required for search |
| Demo fallback | Always-available synthetic data; automatic when live providers unavailable |
| NDVI change detection | rasterio pipeline on COG assets streamed via HTTPS |
| Async jobs | Celery + Redis for large AOIs (> 25 km²); 3-second browser polling |
| Caching | Redis primary + in-process TTLCache fallback |
| Circuit breaker | Per-provider CLOSED / OPEN / HALF-OPEN state machine |
| Retry | tenacity `wait_random_exponential` on all provider calls |

---

## Providers

| Provider | Resolution | Auth required |
|---|---|---|
| `auto` | Best available | Provider-dependent |
| `sentinel2` | 10 m | Copernicus CDSE credentials |
| `landsat` | 30 m | None (search); USGS ERS (bulk download) |
| `demo` | — | None |

See [docs/PROVIDERS.md](docs/PROVIDERS.md) for credential setup.

---

## Project structure

```
app/
  main.py          FastAPI app + DI lifespan (auth, audit, V2 router registration)
  config.py        Flat AppSettings (AppMode enum: demo/staging/production)
  audit_log.py     AuditLoggingMiddleware + append-only JSON audit trail
  dependencies.py  UserRole, UserClaims, HMAC token auth, require_analyst/operator/admin
  metrics.py       In-process metrics registry (counters, histograms, gauges)
  providers/       Sentinel-2, Landsat, Maxar, Planet, Demo, Registry, Base ABC
  services/        AnalysisService, ChangeDetection, SceneSelection, JobManager
  cache/           Redis + TTLCache dual-layer cache
  resilience/      CircuitBreaker, Retry, RateLimiter
  models/          Request / Response / Scene / Job Pydantic models
  routers/         Health, Config, Providers, Analyze, Search, Jobs, Thumbnails, Credits
                   + health_connectors (Track C metrics endpoints)
  workers/         Celery app + run_analysis_task
  static/          Legacy static frontend fallback
src/
  connectors/      STAC (Earth Search, Planetary Computer, CDSE, USGS), GDELT, AIS, OpenSky
  api/             V2 routers: AOIs, Events, Imagery, Playback, Analytics, Exports,
                   Source Health, Orbits, Airspace, Jamming, Strikes, Vessels, Chokepoints,
                   Dark Ships, Intel, Cameras, Detections, Investigations, Absence,
                   Evidence Packs, Analyst
  models/          CanonicalEvent, pilot AOIs, playback, compare, parquet, operational layers
  services/        EventStore, AOI store, playback, export, change analytics,
                   InvestigationService, AbsenceAnalyticsService, EvidencePackService,
                   AnalystQueryService, demo seeder
  storage/         PostGIS ORM + Alembic migration base
  normalization/   Pipeline + deduplication
frontend/
  src/             React + TypeScript app (Vite)
  e2e/             Playwright end-to-end tests
tests/
  conftest.py      Session-scoped shared fixtures
  unit/            All unit tests (backend)
  integration/     All API endpoint tests (V1 + V2)
docs/              Operator docs (API, Architecture, Deployment, Runbook, Alerting, DR …)
```


