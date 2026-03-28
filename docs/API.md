# API Documentation

**Version**: 2.0.0  
**Base URL**: `http://localhost:8000`  
**Authentication**: Optional API Key (see [Auth](#authentication) section)

---

## Authentication

### API Key Methods

The API supports three methods for API key authentication on mutation endpoints (`POST /analyze`, `POST /search`, `DELETE /jobs/{id}/cancel`):

#### 1. Bearer Token (Recommended)
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" https://api.example.com/analyze
```

#### 2. Query Parameter
```bash
curl "https://api.example.com/analyze?api_key=YOUR_API_KEY"
```

#### 3. Cookie
```bash
curl -b "api_key=YOUR_API_KEY" https://api.example.com/analyze
```

### Configuration

Set the `API_KEY` environment variable:
```env
API_KEY=your-secret-key-here
```

**Dev Mode**: If `API_KEY` is empty, authentication is disabled (insecure, development only).  
**Production**: Must set a strong API key, e.g., `openssl rand -hex 32`

---

## Endpoints

### GET /api/health

Service and dependency health check with real-time provider status and circuit breaker state.

#### Response: `HealthResponse`
```json
{
  "status": "ok",
  "mode": "staging",
  "redis": "ok",
  "celery_worker": "ok",
  "providers": {
    "sentinel2": "ok",
    "landsat": "ok",
    "demo": "ok (circuit half-open)"
  },
  "version": "2.0.0"
}
```

#### Fields
- `status`: Always `"ok"` if service is running
- `mode`: `"demo"` | `"staging"` | `"production"` (see [APP_MODE](#app_mode))
- `redis`: `"ok"` | `"unavailable"`
- `celery_worker`: `"ok"` | `"no_workers"` | `"unreachable"` | `"not_configured"`
- `providers`: Dict mapping provider name → status string (includes circuit breaker state if open/half-open)
- `version`: API version

---

### GET /api/config

Returns client configuration, constraints, and operational parameters.

#### Response: `ConfigResponse`
```json
{
  "today": "2026-03-28",
  "min_area_km2": 0.01,
  "max_area_km2": 100,
  "max_lookback_days": 30,
  "supported_providers": ["demo", "sentinel2", "landsat"],
  "app_mode": "staging",
  "async_area_threshold_km2": 25,
  "default_cloud_threshold": 20,
  "cache_ttl_seconds": 3600,
  "redis_available": true,
  "celery_available": true
}
```

#### Fields
- `today`: Fixed reference date (used for temporal window calculations)
- `min_area_km2`, `max_area_km2`: AOI size constraints
- `max_lookback_days`: Maximum history window from `today`
- `supported_providers`: List of available providers
- `app_mode`: Current mode (demo/staging/production)
- `async_area_threshold_km2`: AOIs larger than this auto-promote to async
- `default_cloud_threshold`: Default cloud cover filter (0-100)
- `cache_ttl_seconds`: Cache entry lifetime
- `redis_available`: Whether Redis is accessible
- `celery_available`: Whether Celery worker is reachable

---

### GET /api/providers

Lists all registered providers with availability status.

#### Response: `ProvidersResponse`
```json
{
  "providers": [
    {
      "name": "sentinel2",
      "display_name": "Sentinel-2 (Copernicus Data Space)",
      "available": true,
      "reason": null,
      "resolution_m": 10,
      "notes": ["OAuth2 token obtained", "STAC collection reachable"]
    },
    {
      "name": "landsat",
      "display_name": "Landsat (USGS LandsatLook)",
      "available": true,
      "reason": null,
      "resolution_m": 30,
      "notes": ["No authentication required", "Public STAC endpoint"]
    },
    {
      "name": "demo",
      "display_name": "Demo (Deterministic Fallback)",
      "available": true,
      "reason": null,
      "resolution_m": null,
      "notes": ["Always available", "3 curated construction scenarios"]
    }
  ],
  "demo_available": true
}
```

#### Fields
- `name`: Provider identifier (used in `/analyze` `provider` field)
- `display_name`: User-friendly name
- `available`: True if ready for analysis
- `reason`: Why unavailable (if applicable)
- `resolution_m`: Native resolution in meters (null for demo)
- `notes`: Implementation details

---

### GET /api/credits

Attribution and credit information.

#### Response: `CreditsResponse`
```json
{
  "provider_request_counts": {
    "sentinel2": 42,
    "landsat": 15,
    "demo": 128
  },
  "cache_hit_rate": 0.67,
  "cache_hits": 67,
  "cache_misses": 33,
  "estimated_scenes_fetched": 20
}
```

---

### POST /api/analyze

Run construction activity change detection on a given AOI.

#### Request: `AnalyzeRequest`
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [30.0, 50.0],
        [30.1, 50.0],
        [30.1, 50.1],
        [30.0, 50.1],
        [30.0, 50.0]
      ]
    ]
  },
  "start_date": "2026-02-26",
  "end_date": "2026-03-28",
  "provider": "auto",
  "area_km2": 19.857,
  "cloud_threshold": 20.0,
  "processing_mode": "balanced",
  "async_execution": false
}
```

#### Fields
- `geometry`: GeoJSON Polygon or MultiPolygon (required)
- `start_date`: ISO date (required)
- `end_date`: ISO date (required; must be ≥ start_date)
- `provider`: `"auto"` (default) | `"demo"` | `"sentinel2"` | `"landsat"` (enum)
- `area_km2`: Calculated AOI area (validated against config bounds)
- `cloud_threshold`: 0-100, higher = more cloudy scenes accepted (default: 20)
- `processing_mode`: `"fast"` (minimal processing) | `"balanced"` (recommended) | `"thorough"` (slow)
- `async_execution`: If true, returns job_id immediately; results retrieved via `/api/jobs/{id}`

#### Response: `AnalyzeResponse` (sync) or `{job_id: string}` (async)

**Synchronous response (async_execution=false or area_km2 ≤ threshold):**

```json
{
  "analysis_id": "ana-2026-03-28-001",
  "requested_area_km2": 19.857,
  "provider": "sentinel2",
  "is_demo": false,
  "request_bounds": [30.0, 50.0, 30.1, 50.1],
  "imagery_window": {
    "start": "2026-02-26T00:00:00Z",
    "end": "2026-03-28T23:59:59Z"
  },
  "warnings": [],
  "changes": [
    {
      "change_id": "chg-001",
      "detected_at": "2026-03-28T00:00:00Z",
      "change_type": "Excavation",
      "confidence": 92.5,
      "center": {"lng": 30.05, "lat": 50.05},
      "bbox": [30.04, 50.04, 30.06, 50.06],
      "provider": "sentinel2",
      "summary": "New excavation detected via NDVI decrease in construction zone.",
      "rationale": [
        "Significant NDVI decrease (0.7 → 0.2) indicates vegetation removal",
        "Spatial pattern matches site boundaries",
        "Temporal window aligns with expected construction phase"
      ],
      "before_image": "https://example.com/before.tif",
      "after_image": "https://example.com/after.tif",
      "thumbnail": "https://example.com/thumbnail.png",
      "scene_id_before": "S2A_20260226_001",
      "scene_id_after": "S2A_20260328_001",
      "resolution_m": 10,
      "warnings": []
    }
  ],
  "stats": {
    "total_changes": 1,
    "avg_confidence": 92.5,
    "scenes_analyzed": 2,
    "processing_time_seconds": 12.34
  }
}
```

**Asynchronous response (async_execution=true and area_km2 > threshold):**

```json
{
  "job_id": "job-2026-03-28-abc123",
  "status": "queued"
}
```

#### Status Codes
- `200 OK`: Analysis complete (sync) or job submitted (async)
- `422 Unprocessable Entity`: Invalid geometry, date range, or area
- `503 Service Unavailable`: All providers offline and demo disabled (production mode)

---

### POST /api/search

Search for satellite imagery without running change detection.

#### Request: `SearchRequest`
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]
  },
  "start_date": "2026-02-26",
  "end_date": "2026-03-28",
  "provider": "auto",
  "cloud_threshold": 20.0,
  "max_results": 10
}
```

#### Response: `SearchResponse`
```json
{
  "scenes": [
    {
      "scene_id": "S2A_20260328_001",
      "provider": "sentinel2",
      "satellite": "Sentinel-2A",
      "acquired_at": "2026-03-28T10:30:00Z",
      "cloud_cover": 15.0,
      "bbox": [30.0, 50.0, 30.1, 50.1],
      "resolution_m": 10,
      "asset_urls": {
        "B04": "s3://sentinel-cogs/…/B04.tif",
        "B08": "s3://sentinel-cogs/…/B08.tif"
      }
    }
  ],
  "total": 1,
  "provider": "sentinel2",
  "warnings": []
}
```

---

### GET /api/jobs

List all stored jobs (requires Redis).

#### Response
```json
{
  "jobs": [
    {
      "job_id": "job-…",
      "state": "completed",
      "created_at": "2026-03-28T18:00:00Z",
      "updated_at": "2026-03-28T18:05:00Z"
    }
  ]
}
```

---

### GET /api/jobs/{id}

Retrieve the status and result of a submitted analysis job.

#### Path Parameters
- `id`: Job ID returned from async POST `/api/analyze`

#### Response: `JobStatusResponse`
```json
{
  "job_id": "job-2026-03-28-abc123",
  "state": "completed",
  "result": { /* AnalyzeResponse object */ },
  "error": null,
  "created_at": "2026-03-28T18:00:00Z",
  "updated_at": "2026-03-28T18:05:00Z"
}
```

#### Job States
- `"queued"`: Awaiting worker pickup
- `"running"`: Analysis in progress
- `"completed"`: Success; `result` populated
- `"failed"`: Error; `error` message populated
- `"cancelled"`: User cancelled via DELETE

#### Status Codes
- `200 OK`: Job found
- `404 Not Found`: Job ID not found
- `503 Service Unavailable`: Redis unavailable (jobs not persisted without Redis)

---

### DELETE /api/jobs/{id}

Cancel a queued or running job.

#### Path Parameters
- `id`: Job ID

#### Response
```json
{
  "job_id": "job-…",
  "state": "cancelled",
  "message": "Job cancelled by user"
}
```

#### Status Codes
- `200 OK`: Job cancelled
- `404 Not Found`: Job not found
- `409 Conflict`: Job already completed or failed (cannot cancel)
- `503 Service Unavailable`: Redis unavailable

---

### GET / (Root)

Serves the interactive web UI (Leaflet map + analysis controls).

#### Response
Static HTML + CSS + JavaScript

---

## Data Models

### ChangeRecord
```
change_id              : string (unique identifier)
detected_at            : ISO 8601 datetime
change_type            : string (Excavation, Foundation work, etc.)
confidence             : float [0, 100] (confidence percentage)
center                 : {lng: float, lat: float}
bbox                   : [minLng, minLat, maxLng, maxLat]
provider               : string (origin of detection)
summary                : string (human-readable summary)
rationale              : [string] (explanation steps)
before_image           : string (URL to before scene thumbnail)
after_image            : string (URL to after scene thumbnail)
thumbnail              : string (URL to change-specific thumbnail)
scene_id_before        : string | null (live providers only)
scene_id_after         : string | null (live providers only)
resolution_m           : int | null (native resolution)
warnings               : [string] (caveats for this change)
```

### Geometry Validation

All geometry inputs must be valid GeoJSON:

```json
{
  "type": "Polygon",
  "coordinates": [
    [
      [lng, lat],
      [lng, lat],
      ...
    ]
  ]
}
```

or

```json
{
  "type": "MultiPolygon",
  "coordinates": [
    [[[lng, lat], ...]],
    [[[lng, lat], ...]]
  ]
}
```

**Validation rules:**
- Geometry type: Polygon or MultiPolygon only
- Coordinates: Valid [lng, lat] pairs
- Area: ≥ 0.01 km² and ≤ 100 km²
- Closure: Type=Polygon must have ≥ 3 unique points and close ring

---

## Error Responses

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "geometry"],
      "msg": "Polygon area (150 km²) exceeds max_area_km2 (100)",
      "type": "value_error"
    }
  ]
}
```

### 403 Forbidden (Invalid/Missing API Key)
```json
{
  "detail": "Invalid or missing API key"
}
```

### 503 Service Unavailable
```json
{
  "detail": "No providers available; Redis unavailable for demo fallback"
}
```

---

## Rate Limiting

Implemented via slowapi library:

- `/api/analyze`: 5 requests/minute per IP
- `/api/search`: 10 requests/minute per IP
- `/api/jobs`: 20 requests/minute per IP

Returns `HTTP 429 Too Many Requests` when exceeded.

---

## APP_MODE

The app operates in three modes controlled by the `APP_MODE` environment variable:

| Mode | Providers | Fallback | Use Case |
|------|-----------|----------|----------|
| `demo` | `[demo]` | None | Local testing, no credentials needed |
| `staging` | `[sentinel2, landsat, demo]` | Demo provider | Development; test live providers with fallback |
| `production` | `[sentinel2, landsat]` | None (fail-fast) | Production; requires credentials; no demo |

---

## Examples

### Example 1: Search for Sentinel-2 scenes
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {"type": "Polygon", "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]},
    "start_date": "2026-02-26",
    "end_date": "2026-03-28",
    "provider": "sentinel2",
    "cloud_threshold": 20
  }' | jq
```

### Example 2: Run async analysis with API key
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "geometry": {"type": "Polygon", "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]},
    "start_date": "2026-02-26",
    "end_date": "2026-03-28",
    "async_execution": true
  }' | jq
```

### Example 3: Poll job status
```bash
JOB_ID="job-2026-03-28-abc123"
curl http://localhost:8000/api/jobs/$JOB_ID | jq '.state'
```

---

## Changelog

### v2.0.0 (2026-03-28)
- Added live Sentinel-2 STAC integration (P1-1)
- Added circuit breaker status to `/api/health`
- Added API key authentication (P1-5 / P1-6)
- Documented all 13 endpoints with examples
- Updated response models to include provider metadata
- Added rate limiting documentation

### v1.0.0 (legacy)
- Demo provider only
- Basic change detection endpoint
