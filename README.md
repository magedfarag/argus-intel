# Construction Activity Monitor

A production-ready FastAPI service that detects construction activity by
searching and analysing real satellite imagery (Sentinel-2, Landsat) for a
user-defined area of interest. Falls back to curated demo data when live
credentials are absent.

**Repository:** https://github.com/magedfarag/construction-monitor-demo  
**Tests:** 777 / 791 passing (14 pre-existing skips: Celery/Redis in CI, sentinel2/thumbnails/websocket)  
**Stack:** Python 3.11+ · FastAPI · Pydantic v2 · Celery + Redis · rasterio · Leaflet

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

## How to use

1. Draw a polygon, rectangle, or circle on the map (or type bounding box coords).
2. Keep area between **0.01 km²** and **100 km²** (shown in the status bar).
3. Choose provider, dates, cloud threshold, and processing mode.
4. Click **Analyze**. Results appear with confidence scores, before/after imagery, and rationale.
5. Use the timeline slider to filter detections by recency.

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
  main.py          FastAPI app + DI lifespan
  config.py        Flat AppSettings (pydantic-settings, .env-backed)
  providers/       Sentinel-2, Landsat, Demo, Registry, Base ABC
  services/        AnalysisService, ChangeDetection, SceneSelection, JobManager
  cache/           Redis + TTLCache dual-layer cache
  resilience/      CircuitBreaker, Retry decorator
  models/          Request / Response / Scene / Job Pydantic models
  routers/         7 routers, 13 endpoints
  workers/         Celery app + run_analysis_task
  static/          index.html, app.js, styles.css
src/
  connectors/      STAC, GDELT, AIS, OpenSky, Earth Search, Planetary Computer
  api/             V2 routers: aois, events, exports, imagery, playback, analytics
  models/          CanonicalEvent, pilot AOIs, playback, compare, parquet
  services/        EventStore, AOI store, playback, export, change analytics
  storage/         PostGIS ORM + Alembic migration base
  normalization/   Pipeline + deduplication
tests/
  conftest.py      Session-scoped shared fixtures
  unit/            config, cache, demo provider, scene selection, all V2 modules
  integration/     All API endpoints (V1 + V2)
docs/
  DEPLOYMENT.md    Running in Docker, env vars, production checklist
  PROVIDERS.md     Credential setup for each provider
  CHANGE_DETECTION.md  Pipeline details, scoring, limitations
  API.md           Legacy endpoint reference
  ARCHITECTURE.md  Legacy architecture notes
HANDOVER.md        Full project handover — tasks, decisions, pending work
```

---

## Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

---

## Documentation

| Document | Purpose |
|---|---|
| [HANDOVER.md](HANDOVER.md) | Complete project status, completed work, pending tasks |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, env vars, production checklist |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Sentinel-2 / Landsat credential setup |
| [docs/CHANGE_DETECTION.md](docs/CHANGE_DETECTION.md) | NDVI pipeline, scoring, limitations |
| [docs/API.md](docs/API.md) | Endpoint reference (legacy — refresh pending) |

- Add download, cloud filtering, compositing, and change detection stages
- Persist jobs and outputs if you want asynchronous processing

## Limitations
- The delivered package is a **demo**, not a production detector.
- The current backend does **not** fetch live Sentinel, Landsat, Planet, or Maxar imagery.
- The sample imagery is illustrative and intended for UX demonstration only.
- Area calculation is approximate but sufficient for a demo.
- Circle selections are converted to polygons client-side before submission.

## Suggested next steps
- Add STAC search + authentication for Sentinel and Landsat
- Replace curated detections with a real inference pipeline
- Introduce a job queue for long-running analysis
- Store result artifacts in object storage
- Add parcel overlays, permit feeds, and inspection records for fusion scoring

## References used for architecture choices
- Copernicus Data Space Ecosystem exposes multiple APIs including STAC and other HTTP endpoints for interacting with Sentinel data. See `docs/ARCHITECTURE.md`.
- USGS exposes Landsat access through REST/JSON APIs and STAC-compatible catalog services. See `docs/ARCHITECTURE.md`.
- Leaflet.draw supports polygon, rectangle, and circle drawing in browser clients. See `docs/ARCHITECTURE.md`.
