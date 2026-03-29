# Architecture — Construction Activity Monitor v3.0

**Date**: 2026-03-28  
**Version**: 3.0.0  
**Mode**: FastAPI + Redis + Celery (async jobs) + rasterio (change detection) + PostgreSQL (job persistence)

---

## **System Overview**

```
┌─────────────────┐
│  Browser UI     │  Leaflet map + Turf.js geometry
│  (Static JS)    │  Draws AOI, computes area
└────────┬────────┘
         │ POST /api/analyze (GeoJSON + dates)
         │ WS /api/jobs/{id}/stream (live progress)
         ▼
┌─────────────────────────────────────────────────────┐
│          FastAPI Application                        │
├─────────────────────────────────────────────────────┤
│ • AnalysisService: Orchestrates search → select →   │
│   detect → fallback chain                           │
│ • ProviderRegistry: sentinel2 → landsat → maxar →   │
│   planet → demo (mode-dependent priority)           │
│ • CacheClient: Redis + TTLCache dual-layer         │
│ • CircuitBreaker: Per-provider (Redis or in-memory) │
│ • RateLimiter: 5/10/20 req/min per endpoint        │
│ • JobManager: Redis + PostgreSQL + memory hierarchy │
│ • ThumbnailService: COG→PNG crop with LRU cache    │
│                                                     │
│ Routers:                                            │
│   ├─ health.py: GET /api/health                    │
│   ├─ config_router.py: GET /api/config             │
│   ├─ providers_router.py: GET /api/providers       │
│   ├─ analyze.py: POST /api/analyze (rate-limited)  │
│   ├─ search.py: POST /api/search (rate-limited)    │
│   ├─ jobs.py: GET/DELETE /api/jobs/* (async mgmt)  │
│   ├─ ws_jobs.py: WS /api/jobs/{id}/stream          │
│   ├─ thumbnails.py: GET /api/thumbnails/{id}       │
│   └─ credits.py: GET /api/credits                  │
└────────┬────────────────────────────────────────────┘
         │
    ┌────┴────────┬────────────┬──────────┬──────────────┐
    ▼             ▼            ▼          ▼              ▼
┌────────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ ┌──────────────┐
│   Redis    │ │ Sentinel2│ │Landsat │ │Maxar │ │Demo Provider │
│  (Cache)   │ │ Provider │ │Provider│ │Planet│ │(Deterministic)
└────────────┘ └──────────┘ └────────┘ └──────┘ └──────────────┘
                      │             │
                      └─────┬───────┘
                           ▼
                   ┌────────────────┐
                   │   Rasterio     │
                   │Change Detection│
                   │  (NDVI COGS)   │
                   └────────────────┘
    
    ┌─────────────────────────────────────┐
    │    Celery Worker (Background)        │
    │    Processes async analysis tasks    │
    │    Store results: Redis + PostgreSQL │
    └─────────────────────────────────────┘
    
    ┌─────────────────────────────────────┐
    │    PostgreSQL (Optional)             │
    │    Persistent job history            │
    │    Survives Redis TTL expiry         │
    └─────────────────────────────────────┘
```

---

## **Request Lifecycle**

### Synchronous Path (Small AOI)

```
1. POST /api/analyze
   ├─ Validate geometry (Polygon/MultiPolygon)
   ├─ Validate date range
   ├─ Compute area & check bounds (0.01 - 100 km²)
   ├─ Check cache (Redis or TTLCache)
   │  └─ Hit → return cached AnalyzeResponse
   └─ Miss → proceed to provider selection

2. ProviderRegistry.select_provider()
   ├─ Check CircuitBreaker state per provider
   ├─ Try sentinel2 (if configured & available)
   ├─ Fallback to landsat (if available)
   ├─ Fallback to demo (always available)
   └─ Return selected provider or raise ProviderUnavailableError

3. AnalysisService.run_sync()
   ├─ Call provider.search_imagery()
   │  └─ Fetch STAC scenes from provider
   ├─ Call SceneSelector.select_pair()
   │  └─ Choose before/after scene pair (cloud-weighted)
   ├─ Call ChangeDetectionService.detect_changes()
   │  ├─ Stream COG from provider
   │  ├─ Compute NDVI raster via rasterio
   │  └─ Detect clusters via scikit-image
   ├─ Record result & update metrics
   └─ Cache result (TTL per settings)

4. Return AnalyzeResponse (200 OK)
   ├─ analysis_id, provider, is_demo flag
   ├─ changes[] array with confidence scores
   └─ stats (totals, confidence bounds)
```

### Asynchronous Path (Large AOI or `async_execution=true`)

```
1. POST /api/analyze with async_execution=true
   ├─ Same validation as sync path
   ├─ Generate job_id
   └─ Dispatch to Celery

2. Celery Worker (Background)
   ├─ Receive task (job_id + AnalyzeRequest)
   ├─ Execute same pipeline as sync
   ├─ Store result in Redis + PostgreSQL (write-through)
   ├─ Update job state (pending → running → completed/failed)
   └─ Return job_id to client immediately

3. Client receives updates via WebSocket or HTTP polling:
   ├─ WS /api/jobs/{job_id}/stream (preferred, server-push)
   │  ├─ Receives JSON frames: progress, completed, failed
   │  └─ Auto-closes on terminal state
   └─ GET /api/jobs/{job_id} (fallback, 3s HTTP poll)
      ├─ Return state: "pending" | "running" | "completed" | "failed"
      └─ If completed, include full AnalyzeResponse

4. Client can cancel: DELETE /api/jobs/{job_id}/cancel
   └─ Celery revokes task + terminates worker
```

---

## **Core Modules**

### **Providers** (`backend/app/providers/`)

- **base.py**: `SatelliteProvider` ABC
  - `search_imagery(geometry, dates, cloud_threshold, max_results)`
  - `health_check()` → availability enum
  - Raises `ProviderUnavailableError` on auth/network failure

- **sentinel2.py**: Copernicus Data Space OAuth2 + STAC
  - Requires: `SENTINEL2_CLIENT_ID`, `SENTINEL2_CLIENT_SECRET`
  - Resolution: 10 m (red, NIR) to 60 m (SWIR)

- **landsat.py**: USGS LandsatLook STAC (no auth)
  - Requires: None
  - Resolution: 30 m

- **maxar.py**: Maxar SecureWatch STAC (API key auth)
  - Requires: `MAXAR_API_KEY`
  - Resolution: 0.3–0.5 m (WorldView-3/4)
  - Commercial; subscription required

- **planet.py**: Planet Data API (Basic auth)
  - Requires: `PLANET_API_KEY`
  - Resolution: 3–5 m (PlanetScope), 0.5 m (SkySat)
  - Commercial; daily revisit

- **demo.py**: Deterministic mock (3 hardcoded scenarios)
  - Requires: None
  - Always available; used for testing & fallback

- **registry.py**: Provider priority routing
  - Mode-aware: DEMO (demo only), STAGING (sentinel2→landsat→maxar→planet→demo), PRODUCTION (sentinel2→landsat→maxar→planet)
  - Respects CircuitBreaker state per provider
  - Maintains request counts for credits endpoint

### **Services** (`backend/app/services/`)

- **analysis.py**: `AnalysisService`
  - Orchestrates: cache → search → select → detect → format
  - Handles sync/async dispatch via `JobManager`

- **scene_selection.py**: `SceneSelector`
  - Ranks by: cloud%, recency, scene quality
  - Returns before/after pair for change detection

- **change_detection.py**: `ChangeDetectionService`
  - Streams COG via HTTPS
  - Computes NDVI via rasterio
  - Detects clusters via scikit-image + morphology

- **job_manager.py**: `JobManager`
  - Write-through persistence: Redis → PostgreSQL → Memory
  - Redis: fast ephemeral cache (24h TTL)
  - PostgreSQL: durable persistent store (via SQLAlchemy, optional)
  - In-memory dict: last-resort fallback for local dev
  - Reads check Redis first, then PostgreSQL, then memory

- **postgres_jobs.py**: `PostgresJobStore`
  - SQLAlchemy model for the `jobs` table
  - CRUD with upsert (save/load)
  - Requires `DATABASE_URL` in config

- **thumbnails.py**: `ThumbnailService`
  - Generates PNG crops from COG scenes via rasterio
  - LRU cache (max 128 entries)
  - Graceful degradation: returns None if rasterio unavailable

### **Cache** (`backend/app/cache/`)

- **client.py**: `CacheClient`
  - Primary: Redis (pipelined, atomic key expiry)
  - Fallback: cachetools.TTLCache (in-memory)
  - Methods: `get()`, `set()`, `delete()`, `stats()`, `is_healthy()`
  - TTL configurable via `CACHE_TTL_SECONDS` env

### **Resilience** (`backend/app/resilience/`)

- **circuit_breaker.py**: Per-provider state machine
  - States: CLOSED (normal) → OPEN (failed) → HALF_OPEN (probe)
  - Optional Redis backend for multi-worker state sharing
  - Falls back to in-process memory if Redis unavailable
  - Configurable threshold & recovery timeout
  - Thread-safe via `threading.Lock`

- **retry.py**: Exponential backoff decorator
  - Via tenacity: `@retry(wait=wait_random_exponential(...))`

- **rate_limiter.py**: slowapi integration
  - Limits: 5/min analyze, 10/min search, 20/min jobs
  - Returns HTTP 429 with structured JSON error

### **Models** (`backend/app/models/`)

- **requests.py**: Pydantic v2 request validation
  - `AnalyzeRequest`, `SearchRequest`
  - Geo validation, date validation

- **responses.py**: Pydantic v2 response specification
  - `AnalyzeResponse`, `ChangeRecord`, `JobStatusResponse`
  - Typed stats, warnings, provider metadata

- **jobs.py**: Async job state models
  - `Job`, `JobState` (pending/running/completed/failed/cancelled)

- **scene.py**: Scene metadata
  - `SceneMetadata`: id, provider, satellite, dates, cloud%, bbox, resolution

### **Routers** (`backend/app/routers/`)

- **health.py**: GET /api/health (no auth)
- **config_router.py**: GET /api/config (no auth)
- **providers_router.py**: GET /api/providers (no auth)
- **analyze.py**: POST /api/analyze (auth + rate-limited)
- **search.py**: POST /api/search (auth + rate-limited)
- **jobs.py**: GET/DELETE /api/jobs/{job_id} (auth + rate-limited)
- **ws_jobs.py**: WS /api/jobs/{job_id}/stream (WebSocket live progress)
- **thumbnails.py**: GET /api/thumbnails/{scene_id} (cached PNG crops)
- **credits.py**: GET /api/credits (no auth)

---

## **Data Flow: Change Detection Pipeline**

```
Input: Before/After Scene Pair
  │
  ├─ Before Scene (COG)
  │  ├─ Stream {min, max}-subtiles over HTTPS
  │  └─ Load B4 (red) + B8 (NIR) bands into numpy arrays
  │
  └─ After Scene (COG)
     ├─ Stream {min, max}-subtiles over HTTPS
     └─ Load B4 + B8 bands into numpy arrays

Compute NDVI (Normalized Difference Vegetation Index)
  NDVI = (NIR - RED) / (NIR + RED)
  ├─ Broadcasts over arrays: ~1ms per 512x512
  └─ Range: [-1, +1] (higher = more vegetation)

Compute Difference
  ΔNDVIpixel = NDVIafter[i,j] - NDVIbefore[i,j]
  ├─ Positive: vegetation increased (unlikely in construction)
  └─ Negative: vegetation decreased (construction likely)

Threshold & Binarize
  Mask = ΔNDVIpixel < -0.1 (adjust per region)
  └─ Identifies candidate changed pixels

Morphological Filtering
  ├─ Close: fill interior holes
  ├─ Open: remove small artifacts
  └─ Label connected components

Spatial Clustering
  ├─ Group contiguous pixels
  ├─ Compute cluster centroid & bbox
  ├─ Compute confidence from intensity distribution
  └─ Filter by min_area (suppress noise)

Output: Change Records
  [{
    "change_id": "chg-123",
    "change_type": "Excavation",  // Based on cluster shape + intensity
    "confidence": 87.5,            // % likelihood of construction
    "center": {"lng": 46.67, "lat": 24.72},
    "bbox": [lon_min, lat_min, lon_max, lat_max],
    "rationale": [...]             // Cluster characteristics
  }]
```

---

## **Failure Modes & Fallbacks**

### Provider Unavailable (Network, Auth, Rate Limit)
1. CircuitBreaker records failure
2. After threshold: state → OPEN
3. Requests to provider blocked; try next provider
4. After recovery_timeout: HALF_OPEN (allow 1 probe)
5. If probe succeeds: CLOSED (resume normal)

### Cache & Celery Missing
- Cache fallback: Redis → TTLCache ✅
- Celery fallback: No-op if Redis unavailable; force sync execution ✅
- Both are operational constraints, not errors

### Scene Pair Selection Fails
1. Try next scene pair (ranked by cloud)
2. If none qualify: return warning "low-quality imagery"
3. Demo provider returns synthetic results anyway

---

## **Configuration**

All via environment variables (`.env` file). See `.env.example` for full reference.

```
# App mode: demo | staging | production
APP_MODE=staging

# Providers
SENTINEL2_CLIENT_ID=...                 # Leave empty to skip Sentinel-2
SENTINEL2_CLIENT_SECRET=...
# Landsat: no auth needed for STAC search
MAXAR_API_KEY=...                       # Leave empty to skip Maxar
PLANET_API_KEY=...                      # Leave empty to skip Planet

# Cache
REDIS_URL=redis://localhost:6379        # Leave empty to use TTLCache only
CACHE_TTL_SECONDS=3600

# Database (optional — for persistent job history)
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/construction_monitor

# Celery / Async
CELERY_BROKER_URL=${REDIS_URL}          # Same as REDIS_URL
ASYNC_AREA_THRESHOLD_KM2=25.0          # Trigger async for AOI > 25 km²

# Resilience
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5     # Open after 5 failures
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60     # Try recovery after 60s

# Security
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000
API_KEY=                                # Set to a strong value for production

# Logging
LOG_LEVEL=INFO                          # DEBUG | INFO | WARNING | ERROR
LOG_FORMAT=json                         # or text
```

---

## **Deployment**

- **Docker**: `docker build -t construction-monitor . && docker-compose up`
- **Services**: redis (cache/broker), postgresql (job persistence), api (FastAPI), worker (Celery)
- **Reverse Proxy**: Nginx/HAProxy for:
  - HTTPS termination
  - WebSocket proxying (`Upgrade: websocket`)
  - Rate limiting at CDN level (optional second layer)
  - CORS headers (backup; app enforces primary)
  - Load balancing across multiple API + worker instances

---

## **Future Extensions**

1. **Streaming Tiles**: Replace static scene pair with sliding-window analysis
2. **User Accounts**: Add JWT authentication alongside API keys
3. **Vector Output**: Export change polygons as GeoJSON; integrate with GIS workflows
4. **Multi-Temporal**: Composite 3+ scenes for seasonal suppression
5. **Segmentation**: Deep learning model (U-Net, ResNet) instead of NDVI rules
6. **Dashboard**: Analytics on provider performance, change type distributions, historical trends
