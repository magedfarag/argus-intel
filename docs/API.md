# Construction Activity Monitor — API Reference

**Version**: 2.0.0  
**Base URL**: `http://localhost:8000`  
**Authentication**: API key required (Bearer header, query param `?api_key=`, or cookie)

---

## **Health & Configuration Endpoints** (Public)

### `GET /api/health`

Health check and system status.

**Authentication**: Not required

**Response** (`200 OK`):
```json
{
  "status": "ok",
  "mode": "live",
  "redis": "connected",
  "celery_worker": "ready",
  "providers": {
    "demo": "available",
    "sentinel2": "unavailable",
    "landsat": "available"
  },
  "version": "2.0.0"
}
```

---

### `GET /api/config`

Client configuration and constraints.

**Authentication**: Not required

**Response** (`200 OK`):
```json
{
  "today": "2026-03-28",
  "min_area_km2": 0.01,
  "max_area_km2": 100.0,
  "max_lookback_days": 30,
  "supported_providers": ["demo", "sentinel2", "landsat"],
  "app_mode": "live",
  "async_area_threshold_km2": 50.0,
  "default_cloud_threshold": 20.0,
  "cache_ttl_seconds": 3600,
  "redis_available": true,
  "celery_available": true
}
```

---

### `GET /api/credits`

Usage statistics and cache performance.

**Authentication**: Not required

**Response** (`200 OK`):
```json
{
  "provider_request_counts": {
    "demo": 12,
    "sentinel2": 3,
    "landsat": 8
  },
  "cache_hit_rate": 0.65,
  "cache_hits": 26,
  "cache_misses": 14,
  "estimated_scenes_fetched": 11
}
```

---

### `GET /api/providers`

List available imagery providers.

**Authentication**: Not required

**Response** (`200 OK`):
```json
{
  "providers": [
    {
      "name": "demo",
      "display_name": "Demo (Synthetic Data)",
      "available": true,
      "reason": null,
      "resolution_m": 30,
      "notes": ["No credentials required", "Always available"]
    },
    {
      "name": "sentinel2",
      "display_name": "Sentinel-2 (Copernicus)",
      "available": false,
      "reason": "SENTINEL2_CLIENT_ID not configured",
      "resolution_m": 10,
      "notes": ["Requires OAuth2 credentials", "Free and open data"]
    },
    {
      "name": "landsat",
      "display_name": "Landsat (USGS)",
      "available": true,
      "reason": null,
      "resolution_m": 30,
      "notes": ["No authentication required", "Public domain imagery"]
    }
  ],
  "demo_available": true
}
```

---

## **Analysis Endpoints** (Protected)

### `POST /api/analyze`

Detect construction activity in satellite imagery for an AOI.

**Authentication**: Required (API key)

**Rate Limit**: 5 requests per minute (HTTP 429 if exceeded)

**Request Body**:
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]
    ]
  },
  "start_date": "2026-03-01",
  "end_date": "2026-03-28",
  "provider": "auto",
  "cloud_threshold": 20.0,
  "processing_mode": "balanced",
  "async_execution": false
}
```

**Parameters**:
- `geometry` (required): GeoJSON Polygon or MultiPolygon
- `start_date` (required): ISO 8601 date (YYYY-MM-DD)
- `end_date` (required): ISO 8601 date; must be >= start_date
- `provider` (optional): `auto` | `demo` | `sentinel2` | `landsat` (default: `auto`)
- `cloud_threshold` (optional): 0-100, max acceptable cloud cover % (default: 20)
- `processing_mode` (optional): `fast` | `balanced` | `thorough` (default: `balanced`)
- `async_execution` (optional): If true, return job ticket immediately (default: false)
- `area_km2` (optional): Client-computed area (backend re-validates)

**Response** (`200 OK` — Synchronous):
```json
{
  "analysis_id": "analysis-20260328-abc123",
  "requested_area_km2": 100.0,
  "provider": "demo",
  "is_demo": true,
  "request_bounds": [30.0, 50.0, 30.1, 50.1],
  "imagery_window": {
    "start": "2026-03-01",
    "end": "2026-03-28"
  },
  "warnings": [],
  "changes": [
    {
      "change_id": "chg-123",
      "detected_at": "2026-03-15T10:30:00Z",
      "change_type": "Excavation",
      "confidence": 87.5,
      "center": {"lng": 30.05, "lat": 50.05},
      "bbox": [30.04, 50.04, 30.06, 50.06],
      "provider": "demo",
      "summary": "Large irregular excavation with machinery tracks",
      "rationale": ["Clear soil disturbance", "Geometric irregularity matches equipment activity"],
      "before_image": "/static/assets/change_1_before.png",
      "after_image": "/static/assets/change_1_after.png",
      "thumbnail": "/static/assets/change_1_thumb.png",
      "scene_id_before": "S2A_MSIL2A_20260301...",
      "scene_id_after": "S2A_MSIL2A_20260315...",
      "resolution_m": 10,
      "warnings": []
    }
  ],
  "stats": {
    "total_changes": 3,
    "changes_by_type": {
      "Excavation": 1,
      "Foundation work": 1,
      "Structural assembly": 1
    },
    "confidence_mean": 88.7,
    "confidence_min": 82.3,
    "confidence_max": 91.2
  }
}
```

**Response** (`200 OK` — Asynchronous):
```json
{
  "job_id": "job-20260328-xyz789",
  "state": "pending",
  "result": null,
  "error": null,
  "created_at": "2026-03-28T10:00:00Z",
  "updated_at": "2026-03-28T10:00:00Z"
}
```

**Error Responses**:
- `400`: Invalid geometry, date range, or area bounds
- `422`: Validation error (e.g., Point geometry instead of Polygon)
- `429`: Rate limit exceeded
- `503`: No providers available (app_mode=live)

---

### `POST /api/search`

Search satellite imagery without running analysis.

**Authentication**: Required (API key)

**Rate Limit**: 10 requests per minute (HTTP 429 if exceeded)

**Request Body**:
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]
  },
  "start_date": "2026-03-01",
  "end_date": "2026-03-28",
  "provider": "auto",
  "cloud_threshold": 20.0,
  "max_results": 10
}
```

**Response** (`200 OK`):
```json
{
  "scenes": [
    {
      "scene_id": "S2A_MSIL2A_20260315T101031_N0509_R065_T32UPD_20260315T102021",
      "provider": "sentinel2",
      "satellite": "Sentinel-2A",
      "acquired_at": "2026-03-15T10:10:31Z",
      "cloud_cover": 8.5,
      "bbox": [30.0, 50.0, 30.1, 50.1],
      "resolution_m": 10,
      "asset_urls": {
        "thumbnail": "https://...",
        "visual": "https://...",
        "nir": "https://..."
      }
    }
  ],
  "total": 1,
  "provider": "sentinel2",
  "warnings": []
}
```

---

## **Async Job Endpoints** (Protected)

### `GET /api/jobs/{job_id}`

Poll status of an asynchronous analysis job.

**Authentication**: Required (API key)

**Rate Limit**: 20 requests per minute (HTTP 429 if exceeded)

**Path Parameters**:
- `job_id` (required): Job ID returned by `POST /api/analyze` with `async_execution=true`

**Response** (`200 OK` — Pending):
```json
{
  "job_id": "job-20260328-xyz789",
  "state": "pending",
  "result": null,
  "error": null,
  "created_at": "2026-03-28T10:00:00Z",
  "updated_at": "2026-03-28T10:00:05Z"
}
```

**Response** (`200 OK` — Completed):
```json
{
  "job_id": "job-20260328-xyz789",
  "state": "completed",
  "result": { /* full AnalyzeResponse object */ },
  "error": null,
  "created_at": "2026-03-28T10:00:00Z",
  "updated_at": "2026-03-28T10:03:45Z"
}
```

**Response** (`200 OK` — Failed):
```json
{
  "job_id": "job-20260328-xyz789",
  "state": "failed",
  "result": null,
  "error": "No scenes found matching criteria",
  "created_at": "2026-03-28T10:00:00Z",
  "updated_at": "2026-03-28T10:02:15Z"
}
```

**Possible States**: `pending`, `running`, `completed`, `failed`, `cancelled`

**Error Responses**:
- `429`: Rate limit exceeded
- `503`: Celery/Redis not configured

---

### `DELETE /api/jobs/{job_id}/cancel`

Cancel a pending or running async job.

**Authentication**: Required (API key)

**Path Parameters**:
- `job_id` (required): Job ID to cancel

**Response** (`202 Accepted`):
```json
{
  "job_id": "job-20260328-xyz789",
  "status": "cancellation_requested"
}
```

**Error Responses**:
- `503`: Celery not configured

---

## **Static Content**

### `GET /`

Serves the interactive map UI (index.html).

---

## **Error Response Format**

All errors follow this structure:

```json
{
  "detail": "Human-readable error message",
  "error": "machine_readable_error_code"  // Optional
}
```

**Common HTTP Status Codes**:
- `200`: Success
- `202`: Accepted (async job created)
- `400`: Bad request (invalid data)
- `422`: Validation error (schema mismatch)
- `429`: Rate limit exceeded
- `500`: Internal server error
- `503`: Service unavailable (provider or infrastructure)

---

## **Authentication**

Three methods to provide API key:

1. **Bearer Token** (Recommended):
   ```
   Authorization: Bearer YOUR_API_KEY
   ```

2. **Query Parameter**:
   ```
   GET /api/analyze?api_key=YOUR_API_KEY
   ```

3. **Cookie**:
   ```
   Cookie: api_key=YOUR_API_KEY
   ```

Endpoints marked "Protected" require authentication. Public endpoints do not.

---

## **Rate Limiting**

- `/api/analyze`: 5 requests/minute
- `/api/search`: 10 requests/minute
- `/api/jobs/{job_id}`: 20 requests/minute

Exceeding limits returns HTTP 429 with:
```json
{
  "detail": "Rate limit exceeded. 5 per 1 minute",
  "error": "rate_limit_exceeded"
}
```

---

## **Examples**

### Synchronous Analysis (Demo Provider)
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]
    },
    "start_date": "2026-03-01",
    "end_date": "2026-03-28"
  }'
```

### Asynchronous Analysis (Large AOI)
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {...},
    "start_date": "2026-01-01",
    "end_date": "2026-03-28",
    "async_execution": true
  }'
```

Then poll the job:
```bash
curl -X GET http://localhost:8000/api/jobs/{job_id} \
  -H "Authorization: Bearer YOUR_API_KEY"
```
