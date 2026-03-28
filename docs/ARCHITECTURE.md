# System Architecture — Construction Activity Monitor v2.0

**Version**: 2.0.0 (February-March 2026)  
**Status**: Production-ready with live satellite provider integration  
**Design Pattern**: Layered monolith with resilient provider abstraction

---

## Overview

The system is a **production-grade FastAPI service** that accepts a geographic AOI (Area of Interest) and date range, then returns construction activity changes detected via satellite imagery change detection. It supports both **synchronous** (fast, small areas) and **asynchronous** (large areas, long-running) workflows, with intelligent fallback from live providers (Sentinel-2, Landsat) to a deterministic demo provider.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLIENT: Web Browser (Leaflet Map)                                  │
│  - Draw AOI (polygon/circle)                                        │
│  - Select dates and parameters                                      │
│  - Display results and download GeoJSON                             │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              │ HTTP + GeoJSON
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FASTAPI APPLICATION SERVICE (backend/app/main.py)                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ API ROUTERS (7 modules)                                     │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │ • health.py      → GET /api/health (status + dependencies)  │  │
│  │ • config_router.py → GET /api/config (constraints)          │  │
│  │ • analyze.py     → POST /api/analyze (main entry point)    │  │
│  │ • search.py      → POST /api/search (imagery lookup)        │  │
│  │ • providers_router.py → GET /api/providers (availability)   │  │
│  │ • jobs.py        → GET/DELETE /api/jobs/* (async tracking)  │  │
│  │ • credits.py     → GET /api/credits (attribution)           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ DEPENDENCY INJECTION CONTAINER (dependencies.py)            │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │ • AppSettings (pydantic-settings)                           │  │
│  │ • ProviderRegistry (provider resolution)                    │  │
│  │ • CacheClient (Redis + TTLCache fallback)                   │  │
│  │ • CircuitBreaker (per-provider resilience)                  │  │
│  │ • Celery app (async task queue)                             │  │
│  │ • API Key validator (Bearer/query/cookie auth)              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         ▼                    ▼                    ▼                │
│  ┌─────────────────┐  ┌──────────────┐  ┌─────────────┐          │
│  │   API MODELS    │  │  SERVICES    │  │ RESILIENCE  │          │
│  │ (Pydantic v2)   │  │ LAYER        │  │             │          │
│  ├─────────────────┤  ├──────────────┤  ├─────────────┤          │
│  │                 │  │              │  │             │          │
│  │ • requests.py   │  │ • analysis   │  │ Circuit     │          │
│  │ • responses.py  │  │   service    │  │ Breaker     │          │
│  │ • scene.py      │  │              │  │             │          │
│  │ • jobs.py       │  │ • change_    │  │ Rate        │          │
│  │                 │  │   detection  │  │ Limiter     │          │
│  │                 │  │              │  │             │          │
│  │                 │  │ • scene_     │  │ Retry       │          │
│  │                 │  │   selection  │  │ (tenacity)  │          │
│  │                 │  │              │  │             │          │
│  │                 │  │ • job_       │  │ RateLimiter │          │
│  │                 │  │   manager    │  │             │          │
│  │                 │  │              │  │             │          │
│  └─────────────────┘  └──────────────┘  └─────────────┘          │
│                              △                                     │
│                              │                                     │
│         ┌────────────────────┼────────────────────┐               │
│         ▼                    ▼                    ▼               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  PROVIDER ABSTRACTION LAYER (providers/)               │    │
│  ├─────────────────────────────────────────────────────────┤    │
│  │                                                         │    │
│  │  ┌────────────────┐  ┌────────────────┐  ┌──────────┐  │    │
│  │  │ Sentinel2      │  │ Landsat        │  │ Demo     │  │    │
│  │  │ Provider       │  │ Provider       │  │ Provider │  │    │
│  │  ├────────────────┤  ├────────────────┤  ├──────────┤  │    │
│  │  │ • OAuth2       │  │ • Public STAC  │  │ • 3      │  │    │
│  │  │   token cache  │  │   (no auth)    │  │   hardcoded  │    │
│  │  │ • STAC search  │  │ • STAC search  │  │   scenarios  │    │
│  │  │ • COG stream   │  │ • Landsat API  │  │ • Always     │    │
│  │  │   (rasterio)   │  │                │  │   available  │    │
│  │  └────────────────┘  └────────────────┘  └──────────┘  │    │
│  │                             △                           │    │
│  │        ┌────────────────────┼────────────────────┐      │    │
│  │        │ All inherit from   │ Sentinel2/Landsat │      │    │
│  │        │ SatelliteProvider  │ extend with       │      │    │
│  │        │ (base.py)          │ live COG support   │      │    │
│  │        └────────────────────┼────────────────────┘      │    │
│  │                             │                           │    │
│  │        Provider Registry (registry.py)                  │    │
│  │        ─────────────────────────────────────            │    │
│  │        Priority chain by APP_MODE:                      │    │
│  │         • demo: [demo]                                  │    │
│  │         • staging: [sentinel2, landsat, demo]           │    │
│  │         • production: [sentinel2, landsat] (fail-fast)  │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                     │
└──────────────────────────────┼─────────────────────────────────────┘
                               │
                 ┌─────────────┼──────────────┐
                 ▼             ▼              ▼
            ┌─────────┐   ┌─────────────┐   ┌──────────┐
            │ REDIS   │   │ EXTERNAL    │   │ STATIC   │
            │ (Cache+ │   │ STAC APIs   │   │ ASSETS   │
            │  Queue+ │   │             │   │ (HTML,   │
            │  Jobs)  │   │ Copernicus  │   │ CSS,JS)  │
            │         │   │ Data Space  │   │          │
            │ Optional│   │             │   │ Local    │
            │ (falls  │   │ USGS        │   │ serving  │
            │ back to │   │ LandsatLook │   │          │
            │ memory) │   │             │   │          │
            └─────────┘   │ AWS S3      │   └──────────┘
                          │ (COG assets)│
                          └─────────────┘
```

---

## Request Lifecycle — Synchronous Analysis

```
Browser POST /api/analyze {geometry, dates, provider, async_execution: false}
  │
  ▼
analyze.py router:
  • Validate Pydantic request
  • Check area bounds (0.01-100 km²)
  • Check date order (start ≤ end)
  • If area > ASYNC_AREA_THRESHOLD → promote to async
  │
  ▼
AnalysisService.run_sync():
  │
  ├─ CACHE LOOKUP
  │  └─ Hit? → return cached AnalyzeResponse [DONE]
  │
  ├─ PROVIDER SELECTION (registry.select_provider())
  │  └─ Try providers in priority order per APP_MODE
  │
  ├─ For each provider attempt:
  │  │
  │  ├─ CHECK CIRCUIT BREAKER
  │  │  └─ is_open()? → skip to next provider
  │  │
  │  ├─ TRY LIVE ANALYSIS (_run_live_analysis)
  │  │  │
  │  │  ├─ search_imagery() [+tenacity retry]
  │  │  │  └─ Could be Sentinel2.search_scenes() [OAuth2 + STAC]
  │  │  │     or Landsat.search_scenes() [public STAC]
  │  │  │
  │  │  ├─ [ If ≥1 scene found ]
  │  │  │  ├─ rank_scenes() [weighted score on cloud/recency/overlap]
  │  │  │  │
  │  │  │  ├─ select_scene_pair() [pick best before/after pair]
  │  │  │  │
  │  │  │  ├─ run_change_detection() [rasterio COG streaming + NDVI pipeline]
  │  │  │  │  └─ Could fail gracefully (rasterio unavailable)
  │  │  │  │
  │  │  │  ├─ CircuitBreaker.record_success(provider)
  │  │  │  └─ Return AnalyzeResponse {is_demo: false, changes: [...]}
  │  │  │
  │  │  └─ [ If error during search/detection ]
  │  │     └─ CircuitBreaker.record_failure(provider)
  │  │        └─ Try next provider (fallback chain)
  │  │
  │  └─ Success → break fallback loop
  │
  └─ [ If all live providers failed/unavailable ]
     │
     ├─ APP_MODE=production? → raise 503 ServiceUnavailable
     │
     └─ DemoProvider.search_imagery()
        └─ Return hardcoded AnalyzeResponse {is_demo: true, changes: [...]}
           (3 curated construction scenarios for fixed test AOI)

CACHE WRITE (if not from cache)
│
▼
Return 200 + AnalyzeResponse JSON
```

---

## Provider Priority & Fallback Chain

```
APP_MODE Control: $APP_MODE environment variable

┌──────────────────────────────────────────────────────────────┐
│ DEMO MODE (development/local)                               │
├──────────────────────────────────────────────────────────────┤
│ Provider Order: [demo]                                       │
│ Fallback: None (demo always available)                       │
│ Use Case: Local dev, no credentials needed                   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ STAGING MODE (development/testing with live providers)       │
├──────────────────────────────────────────────────────────────┤
│ Provider Order: [sentinel2, landsat, demo]                   │
│ Fallback: Demo provider (always available)                   │
│ Use Case: Test live providers; demo masks intermittent fails │
│                                                              │
│ Sentinel-2 [Copernicus Data Space]                           │
│   ├─ Requires: SENTINEL2_CLIENT_ID + SENTINEL2_CLIENT_SECRET │
│   ├─ Resolution: 10 m                                        │
│   └─ Revisit: 5 days (Twin constellation A+B)               │
│                                                              │
│ Landsat [USGS LandsatLook STAC]                              │
│   ├─ Requires: None (public data)                            │
│   ├─ Resolution: 30 m (panchromatic 15 m)                   │
│   └─ Revisit: 16 days (Landsat 8/9)                         │
│                                                              │
│ Demo [Deterministic]                                         │
│   ├─ Requires: None                                          │
│   ├─ Scenarios: 3 fixed construction activity changes        │
│   └─ Use: Develop UI, test async workflow                   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ PRODUCTION MODE (production deployment)                      │
├──────────────────────────────────────────────────────────────┤
│ Provider Order: [sentinel2, landsat]                         │
│ Fallback: None (fail-fast if unavailable)                    │
│ Use Case: Production; requires credentials; transparency    │
│                                                              │
│ Fail-Fast Behavior:                                          │
│   ├─ All live providers unavailable                          │
│   ├─ All live providers offline (circuit breaker open)       │
│   └─ → Return 503 Service Unavailable (no demo fallback)     │
└──────────────────────────────────────────────────────────────┘
```

---

## Circuit Breaker State Machine

```
Per-Provider State Tracking (thread-safe):

┌─────────────────────────────────┐
│         CLOSED (initial)        │
│    Normal operation; accept     │
│    requests to provider         │
└──────────────┬──────────────────┘
               │
      N failure events (failure_threshold=5)
               │
               ▼
┌─────────────────────────────────┐
│         OPEN                    │
│  Block requests to provider;    │
│  count failures until timeout   │
└──────────────┬──────────────────┘
               │
      recovery_timeout=60 seconds elapsed
               │
               ▼
┌─────────────────────────────────┐
│      HALF-OPEN (probe)          │
│  Allow 1 request to probe       │
│  provider recovery              │
└──────────────┬──────────────────┘
               │
    ┌──────────┴──────────┐
    │ Success?            │ Failure?
    ▼                     ▼
┌─────────────────┐  ┌──────────────┐
│ CLOSED (reset)  │  │ OPEN (retry) │
└─────────────────┘  └──────────────┘
```

Per-provider isolation:
- Sentinel-2 open ≠ Landsat open
- Each provider tracked independently
- In-process state (single worker); consider Redis for multi-worker deployments

---

## Request Lifecycle — Asynchronous Analysis

```
Browser POST /api/analyze {async_execution: true, area_km2: 50}
  │
  ▼
analyze.py router:
  • area_km2 > ASYNC_AREA_THRESHOLD (25 km²) → auto-promote to async
  • OR async_execution=true in request
  │
  ▼
JobManager.create_job() [Redis-backed or in-memory]
  • Create Job(id, state="queued", ...)
  • Enqueue Celery task: tasks.run_analysis_task
  │
  ▼
Return 202 Accepted {job_id, status: "queued"}
  
┌──────────────────────────────────────────────────────────────┐
│ Browser Polls: GET /api/jobs/{job_id}                        │
│ ├─ Every 3 seconds                                           │
│ ├─ Display job state badge                                  │
│ └─ When completed, render AnalyzeResponse                   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Celery Worker (background task)                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ tasks.run_analysis_task(job_id, request_dict):              │
│  • JobManager.get_job(job_id)                               │
│  • Update state → "running"                                 │
│  • Call AnalysisService.run_sync()                          │
│  │ └─ Same fallback chain as sync (above)                  │
│  │                                                          │
│  ├─ [ If successful ]                                      │
│  │  └─ JobManager.update_job(state="completed", result=...) │
│  │                                                          │
│  └─ [ If exception ]                                       │
│     └─ JobManager.update_job(state="failed", error=...)     │
│                                                              │
│ Job persisted in Redis (TTL: 24h) or in-memory dict         │
└──────────────────────────────────────────────────────────────┘
```

---

## Caching Strategy

```
Two-Layer Cache (Redis Primary + TTLCache Fallback)

┌───────────────────────────────────────────────────────────┐
│ CacheClient (cache/client.py)                              │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  try:                                                    │
│    redis_client.connect(timeout=3s)                      │
│    → REDIS PRIMARY [distributed, persistent]            │
│  except:                                                 │
│    → TTLCACHE FALLBACK [in-memory, per-process]          │
│                                                           │
│  Operations:                                             │
│  • set(key, value, ttl=3600)  → serialize to JSON        │
│  • get(key) → deserialize from JSON                      │
│  • delete(key)                                           │
│  • stats() → {backend: "redis"|"memory", hits, misses}  │
│  • is_healthy() → True if backend responsive            │
│                                                           │
│  Serialization: JSON (handles datetime, dict, list)      │
│                                                           │
└───────────────────────────────────────────────────────────┘

Cache Key Structure:
  "analysis:{geometry_hash}:{start_date}:{end_date}:{cloud_threshold}"
  
Example:
  "analysis:abc123:2026-02-26:2026-03-28:20"
  
TTL: Configurable; default 3600 seconds (1 hour)
```

---

## Service Layers

### 1. **Analysis Service** (`backend/app/services/analysis.py`)

Orchestrates the entire change detection workflow:
- Manages provider fallback chain
- Coordinates scene search, selection, and detection
- Integrates with circuit breaker and cache
- Converts exceptions to user-friendly errors

### 2. **Change Detection Service** (`backend/app/services/change_detection.py`)

Implements NDVI (Normalized Difference Vegetation Index) pipeline:
- Opens remote GeoTIFF assets (COGs) via rasterio
- Computes NDVI: (NIR - RED) / (NIR + RED)
- Detects changes via morphological filtering
- Returns GeoJSON polygon features with confidence scores

Graceful degradation: If rasterio unavailable, returns empty changes list + warning

### 3. **Scene Selection Service** (`backend/app/services/scene_selection.py`)

Selects best satellite scenes via composite scoring:
- **Cloud weight (40%)**: Lower cloud cover preferred
- **Recency weight (35%)**: More recent scenes preferred
- **Overlap weight (25%)**: Maximum AOI overlap preferred

Selects before/after pair with ≥7-day temporal gap

### 4. **Job Manager Service** (`backend/app/services/job_manager.py`)

Manages async job lifecycle:
- Create, read, update, delete jobs
- Store in Redis (distributed) or in-memory dict (fallback)
- 24-hour TTL (jobs expire after 1 day)

---

## Resilience Patterns

### Circuit Breaker
Per-provider failure tracking prevents cascading failures:
- **CLOSED**: Normal operation
- **OPEN**: After 5 consecutive failures, block requests for 60 seconds
- **HALF-OPEN**: After 60 seconds, allow 1 probe request
- For isolation demo→sentinel2 failure ≠ landsat failure

### Retry Strategy
`tenacity` library with exponential backoff + jitter:
- Max 3 attempts per provider
- Prevents thundering herd on rate-limited endpoints
- Random jitter prevents synchronized retries

### Graceful Degradation
- Live provider unavailable → try next provider
- All live providers fail → fall back to demo (staging mode)
- Production mode → fail fast (no demo)
- Rasterio unavailable → return empty changes + warning

---

## Configuration Management

### AppSettings (Pydantic v2)
```python
class AppSettings(BaseSettings):
    # Mode
    app_mode: str = "staging"  # demo | staging | production
    
    # Sentinel-2
    sentinel2_client_id: str = ""
    sentinel2_client_secret: str = ""
    sentinel2_token_url: str = "https://identity.dataspace.copernicus.eu/..."
    sentinel2_stac_url: str = "https://catalogue.dataspace.copernicus.eu/..."
    
    # Redis
    redis_url: str = ""  # e.g., redis://localhost:6379/0
    
    # Constraints
    min_area_km2: float = 0.01
    max_area_km2: float = 100
    max_lookback_days: int = 30
    
    # Behavior
    async_area_threshold_km2: float = 25  # Auto-promote to async
    default_cloud_threshold: float = 20
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    cache_ttl_seconds: int = 3600
    
    # API Security
    api_key: str = ""  # Optional; empty = insecure dev mode
    allowed_origins: str = "http://localhost:3000,..."
```

All settings read from `.env` file (see `.env.example`)

---

## Deployment

### Docker Compose (Recommended)
```yaml
services:
  redis:
    image: redis:7-alpine
    ports: [6379]
    healthcheck: redis-cli ping
    
  api:
    build: .
    environment:
      REDIS_URL: redis://redis:6379/0
      SENTINEL2_CLIENT_ID: ...
      SENTINEL2_CLIENT_SECRET: ...
      APP_MODE: production
    ports: [8000]
    depends_on: [redis]
    
  worker:
    build: .
    environment: [REDIS_URL, SENTINEL2_*, APP_MODE]
    command: celery -A backend.app.workers.celery_app worker
    depends_on: [redis]
```

### Multi-worker Scaling
- Each worker runs independently
- Circuit breaker state is per-process (isolation)
- For multi-worker shared state, replace CircuitBreaker with Redis-backed implementation
- Jobs persist in Redis (shared across workers)

---

## Module Structure

```
backend/
├── app/
│   ├── main.py                     FastAPI app + lifespan DI
│   ├── config.py                   AppSettings + env loading
│   ├── dependencies.py             DI container + auth
│   ├── logging_config.py           JSON structured logging
│   │
│   ├── providers/
│   │   ├── base.py                 SatelliteProvider ABC
│   │   ├── sentinel2.py            OAuth2 + STAC
│   │   ├── landsat.py              USGS public STAC
│   │   ├── demo.py                 Deterministic fallback
│   │   └── registry.py             Provider resolution + priority
│   │
│   ├── services/
│   │   ├── analysis.py             Orchestrator service
│   │   ├── change_detection.py     Rasterio NDVI pipeline
│   │   ├── scene_selection.py      Scene ranking + pairing
│   │   └── job_manager.py          Async job CRUD
│   │
│   ├── cache/
│   │   └── client.py               Redis + TTLCache
│   │
│   ├── resilience/
│   │   ├── circuit_breaker.py      Per-provider state machine
│   │   └── retry.py                Tenacity + jitter
│   │
│   ├── models/
│   │   ├── requests.py             Pydantic request models
│   │   ├── responses.py            Pydantic response models
│   │   ├── scene.py                SceneMetadata dataclass
│   │   └── jobs.py                 Job + JobState
│   │
│   ├── routers/
│   │   ├── analyze.py              POST /api/analyze
│   │   ├── search.py               POST /api/search
│   │   ├── health.py               GET /api/health
│   │   ├── config_router.py         GET /api/config
│   │   ├── providers_router.py      GET /api/providers
│   │   ├── jobs.py                 GET/DELETE /api/jobs/*
│   │   └── credits.py              GET /api/credits
│   │
│   ├── workers/
│   │   ├── celery_app.py           Celery instance
│   │   └── tasks.py                Async task: run_analysis_task
│   │
│   └── static/
│       ├── index.html              Interactive web UI
│       ├── app.js                  Client-side logic
│       └── styles.css              Dark theme

tests/
├── unit/                           Unit tests (38+)
├── integration/                    Integration tests (11+)
└── conftest.py                     Shared fixtures

docs/
├── API.md                          Endpoint reference
├── ARCHITECTURE.md                 This file
├── DEPLOYMENT.md                   Operational guide
├── PROVIDERS.md                    Credential setup
└── CHANGE_DETECTION.md             Pipeline reference
```

---

## Known Limitations & Future Work

### Current Limitations
1. **CircuitBreaker state** is per-process (not shared across workers)
   - Solution: Replace with Redis-backed implementation for multi-worker deployments

2. **Change detection** returns empty list if rasterio unavailable
   - Workaround: Dockerfile installs libgdal32 by default
   - Solution: Pin GDAL version to match OS package manager

3. **Area calculation** uses flat-earth approximation
   - Impact: ±2% error for small AOIs; acceptable for demo
   - Solution: Use geospatial library (e.g., geopandas) for production

4. **Demo provider** has only 3 hardcoded scenarios
   - Impact: Limited test coverage for edge cases
   - Solution: Expand demo scenario library or use randomized geometry

### Future Enhancements (P3+)
1. **Multi-source fusion**: Combine Sentinel-2 + Landsat results
2. **Cloud-native object storage**: Persist scene thumbnails to S3/GCS
3. **Database**: Replace in-memory JobManager with PostgreSQL
4. **WebSocket support**: Replace 3s polling with live updates
5. **Commercial providers**: Add Maxar/Planet integrations
6. **Advanced algorithms**: Train ML models for change classification
7. **Team collaboration**: Share AOIs and results between users

---

## Security Considerations

- **API Key**: Optional in dev mode; mandatory in production
- **HTTPS**: Use TLS in production; configure in reverse proxy (nginx)
- **CORS**: Configurable; default allows localhost only
- **Credentials**: Stored in `.env` (✅ in `.gitignore`); never in code
- **Rate Limiting**: Per-endpoint limits prevent abuse
- **Non-root user**: Docker runs as `appuser` (OWASP A05)

---

## Performance Notes

**Change Detection Latency**:
- Small AOI (< 25 km²): ~5-15 seconds (sync)
- Large AOI (> 25 km²): ~30-120 seconds (async), worker-dependent

**Scene Search Latency**:
- Sentinel-2 STAC: 2-5 seconds (depends on OAuth token cache)
- Landsat public STAC: 5-10 seconds
- Demo: < 100 ms (lookup in memory)

**Cache Effectiveness**:
- Same AOI, date range, cloud threshold: 100% cache hit (< 10 ms)
- Different AOI or dates: Cache miss (full analysis required)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.0.0 | Mar 2026 | Live Sentinel-2 + Landsat, circuit breaker, async jobs, rate limiting |
| 1.0.0 | Feb 2026 | Demo provider only, basic sync analysis |

---

**Last Updated**: 2026-03-28  
**Maintainer**: GitHub Copilot (Principal Engineer)  
**License**: (See LICENSE file)
