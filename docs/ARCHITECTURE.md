# Architecture — ARGUS Multi-Domain Surveillance Intelligence v6.0

**Date**: 2026-04-04  
**Version**: 6.0.0  
**Mode**: FastAPI + React + Redis + Celery + rasterio + PostgreSQL  
**Status**: Production Release Candidate — all 6 transformation phases complete

> See [docs/DATA_RETENTION_POLICY.md](DATA_RETENTION_POLICY.md) for data governance and retention rules.  
> See [docs/RUNBOOK.md](RUNBOOK.md) for operational runbooks.  
> See [docs/ALERTING_RULES.md](ALERTING_RULES.md) for monitoring configuration.

---

## Application Mode (`APP_MODE`)

The platform has three operating modes controlled by the `APP_MODE` environment variable:

| Mode | Value | Behaviour |
|---|---|---|
| Demo | `demo` | Always uses `DemoProvider` — no live data, no credentials needed. Auth role-checks bypassed. |
| Staging | `staging` | Real providers with demo fallback. Auth enforced when `API_KEY` is set. Default. |
| Production | `production` | Real providers only — no demo fallback. Any provider failure raises an error. Auth always enforced. |

```python
class AppMode(str, Enum):
    DEMO       = "demo"
    STAGING    = "staging"
    PRODUCTION = "production"
```

---

## Authentication and RBAC (Phase 6 Track A)

All privileged API surfaces are protected by HMAC-SHA256 signed tokens defined in `app/dependencies.py`.

### Roles

| Role | Numeric level | Capabilities |
|---|---|---|
| `analyst` | 1 | Read all data, query briefings, list investigations |
| `operator` | 2 | Analyst + create/update/delete investigations and signals |
| `admin` | 3 | Operator + administrative operations |

Role hierarchy is additive: a higher role satisfies any lower-role check.

### Token format

```
base64url(payload_json).base64url(HMAC-SHA256(payload_json, JWT_SECRET))
```

Tokens are issued by `create_access_token(user_id, role)` and verified by `get_current_user()`.

### Demo and dev bypass

- `APP_MODE=demo` — all role checks bypass; all requests treated as `admin`.
- `API_KEY` not set (dev mode) — all requests treated as `admin`.
- Raw `API_KEY` match maps to `analyst` role.
- `ADMIN_API_KEY` / `OPERATOR_API_KEY` / `ANALYST_API_KEY` env vars enable direct tiered key issuance.

### Audit logging

`AuditLoggingMiddleware` (registered on `app` in `main.py`) logs every request to the `argus.audit` logger:

- JSON-formatted append-only entries via `app/audit_log.py`
- `user_id` stored as 16-char SHA-256 prefix (no cleartext PII)
- Runs as a `BackgroundTask` — zero request-path latency impact

See `docs/DATA_RETENTION_POLICY.md` for audit log retention requirements.

---

## Metrics and Observability (Phase 6 Track C)

In-process metrics registry in `app/metrics.py`:

- **Counters**: `http_requests_total`, `http_errors_total`, `connector_errors_total`, `analysis_total`
- **Histograms**: `http_request_duration_seconds`, `replay_query_duration_seconds`
- **Gauges**: `connector_last_fetch_timestamp`

Exposed at `/api/v1/health/connectors` (per-connector health) and `/api/v1/health/metrics` (snapshot).

Prometheus scrape endpoint at `/metrics` (requires `prometheus-fastapi-instrumentator`).

Background health prober runs every 5 minutes and probes all registered STAC catalogs + GDELT + OpenSky.

See `docs/ALERTING_RULES.md` for the 8 Prometheus alerting rules and `docs/RUNBOOK.md` for incident response procedures.

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
│ V1 Routers (app/routers/):                          │
│   ├─ health.py:          GET /api/health            │
│   ├─ health_connectors:  GET /api/v1/health/connectors, /metrics│
│   ├─ config_router.py:   GET /api/config            │
│   ├─ providers_router.py: GET /api/providers        │
│   ├─ analyze.py:         POST /api/analyze          │
│   ├─ search.py:          POST /api/search           │
│   ├─ jobs.py:            GET/DELETE /api/jobs/*     │
│   ├─ ws_jobs.py:         WS /api/jobs/{id}/stream   │
│   ├─ thumbnails.py:      GET /api/thumbnails/{id}   │
│   └─ credits.py:         GET /api/credits           │
│                                                     │
│ V2 Routers (src/api/) — see API table for all paths:│
│   AOIs, Events, Imagery, Playback, Analytics,       │
│   Exports, Source Health, Orbits, Airspace,         │
│   Jamming, Strikes, Vessels, Chokepoints,           │
│   Dark Ships, Intel, Cameras, Detections,           │
│   Investigations, Absence, Evidence Packs, Analyst  │
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

- **Docker**: `docker build -t argus-intel . && docker-compose up`
- **Services**: redis (cache/broker), postgresql (job persistence), api (FastAPI), worker (Celery)
- **Reverse Proxy**: Nginx/HAProxy for:
  - HTTPS termination
  - WebSocket proxying (`Upgrade: websocket`)
  - Rate limiting at CDN level (optional second layer)
  - CORS headers (backup; app enforces primary)
  - Load balancing across multiple API + worker instances

---

## **V2 Operational and Intelligence Layers (src/)**

All V2 services share an in-memory `EventStore` seeded at startup by `src/services/demo_seeder.py`.

### **Unified Data Plane** (`src/`)

| Module | Purpose |
|---|---|
| `src/connectors/` | STAC (Earth Search, Planetary Computer, CDSE Sentinel-2, USGS Landsat), GDELT, AIS, OpenSky |
| `src/services/event_store.py` | Canonical in-memory event store shared by all V2 routers |
| `src/services/playback.py` | Time-window slice queries; 24h / 7d / 30d replay windows |
| `src/services/change_analytics.py` | Cross-event trend analysis |
| `src/normalization/pipeline.py` | Deduplication + ingestion pipeline |

### **Operational Layers (Phase 2)**

| Router | Prefix | Description |
|---|---|---|
| `src/api/orbits.py` | `/api/v1/orbits` | Satellite pass predictions; TLE-based flat-earth approximation |
| `src/api/airspace.py` | `/api/v1/airspace` | No-fly zones, airspace violations, NOTAM alerts |
| `src/api/jamming.py` | `/api/v1/jamming` | GPS / GNSS jamming events; affected-arc queries |
| `src/api/strike.py` | `/api/v1/strikes` | Strike reconstruction events; evidence attachment |

### **Maritime Intelligence (Phase 6 Maritime)**

| Router | Prefix | Description |
|---|---|---|
| `src/api/vessels.py` | `/api/v1/vessels` | Vessel registry lookup by MMSI / IMO |
| `src/api/chokepoints.py` | `/api/v1/chokepoints` | Chokepoint transit density |
| `src/api/dark_ships.py` | `/api/v1/dark-ships` | AIS gap / dark-ship detection |
| `src/api/intel.py` | `/api/v1/intel` | Aggregated intelligence briefing |

### **Sensor Fusion (Phase 4)**

| Router | Prefix | Description |
|---|---|---|
| `src/api/cameras.py` | `/api/v1/cameras` | Camera feed inventory; nearest observation by time |
| `src/api/detections.py` | `/api/v1/detections` | Detection overlays (confidence radius, click popups) |

**Camera observation model**: `CameraObservation` records bearing, elevation, and confidence for each camera-entity pair.  Nearest observations to `currentTime` drive the frontend highlight pass.

### **Investigation Workflows (Phase 5)**

| Router | Prefix | Auth | Description |
|---|---|---|---|
| `src/api/investigations.py` | `/api/v1/investigations` | GET: analyst; POST/PUT/DELETE: operator | Saved investigations with sub-resource evidence and AOI linking |
| `src/api/evidence_packs.py` | `/api/v1/evidence-packs` | operator | Evidence pack generation and ZIP download |
| `src/api/analyst.py` | `/api/v1/analyst` | GET: analyst; POST: operator | Saved queries and AI briefing generation |
| `src/api/absence.py` | `/api/v1/absence` | GET: analyst; POST: operator | Absence-as-signal analytics; AIS gap detection |

### **Source Health Dashboard (Phase 5 / Track C)**

| Router | Prefix | Description |
|---|---|---|
| `src/api/source_health.py` | `/api/v1/health` | Full dashboard, per-connector status, SLA alerts |
| `app/routers/health_connectors.py` | `/api/v1/health` | Per-connector health + in-process metrics snapshot |

---

## **Future Extensions**

1. **Postgres persistence**: Replace in-memory AOI, event, investigation stores with PostGIS
2. **Redis caching**: Replace per-worker in-process rate limiter with shared Redis state
3. **External identity provider**: Replace HMAC-self-signed tokens with OAuth2 / OIDC
4. **Live connector activation**: Activate AIS, OpenSky, GDELT connectors with real credentials
5. **3D terrain streaming**: Replace flat-earth orbit approximations with WGS-84 ellipsoid model
6. **Streaming tiles**: Sliding-window analysis instead of before/after scene pair
