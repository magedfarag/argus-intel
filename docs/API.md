# API Reference — Construction Activity Monitor v3.0

**Base URL**: `http://localhost:8000` (development)  
**Version**: 3.0.0  
**Authentication**: Optional API key via Bearer token, query param, or cookie (required if `API_KEY` is set)

---

## **Health & Status**

### `GET /api/health`
Check API and dependency health (no auth required).

**Request**:
```bash
curl http://localhost:8000/api/health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2026-03-28T10:15:00Z",
  "dependencies": {
    "redis": "healthy",
    "sentinel2_provider": "healthy",
    "landsat_provider": "unhealthy",
    "maxar_provider": "unavailable",
    "planet_provider": "unavailable",
    "demo_provider": "healthy"
  }
}
```

---

### `GET /api/config`
Retrieve application configuration (no auth required).

**Request**:
```bash
curl http://localhost:8000/api/config
```

**Response** (200 OK):
```json
{
  "app_mode": "staging",
  "cache_enabled": true,
  "async_enabled": true,
  "async_area_threshold_km2": 25.0,
  "supported_providers": ["sentinel2", "landsat", "maxar", "planet", "demo"],
  "available_providers": ["landsat", "demo"],
  "max_area_km2": 100.0,
  "min_area_km2": 0.01,
  "max_date_range_days": 365,
  "rate_limits": {
    "analyze": "5 per 1 minute",
    "search": "10 per 1 minute",
    "jobs": "20 per 1 minute"
  }
}
```

---

### `GET /api/providers`
List available satellite providers and their current status (no auth required).

**Request**:
```bash
curl http://localhost:8000/api/providers
```

**Response** (200 OK):
```json
{
  "providers": [
    {
      "id": "sentinel2",
      "name": "Sentinel-2 (Copernicus)",
      "available": false,
      "status": "OPEN",
      "last_failure": "2026-03-28T09:45:00Z",
      "resolution_m": 10,
      "latency_ms": 1250
    },
    {
      "id": "landsat",
      "name": "Landsat 8/9 (USGS)",
      "available": true,
      "status": "CLOSED",
      "resolution_m": 30,
      "latency_ms": 850
    },
    {
      "id": "maxar",
      "name": "Maxar (SecureWatch)",
      "available": false,
      "status": "CLOSED",
      "resolution_m": 0.5,
      "notes": ["Requires MAXAR_API_KEY", "Commercial high-resolution (0.3-0.5 m)"]
    },
    {
      "id": "planet",
      "name": "Planet (PlanetScope/SkySat)",
      "available": false,
      "status": "CLOSED",
      "resolution_m": 3,
      "notes": ["Requires PLANET_API_KEY", "Daily revisit at 3-5 m resolution"]
    },
    {
      "id": "landsat",
      "name": "Landsat 8/9 (USGS)",
      "available": true,
      "status": "CLOSED",
      "last_success": "2026-03-28T10:10:00Z",
      "resolution_m": 30,
      "latency_ms": 850
    },
    {
      "id": "demo",
      "name": "Demo Provider (Mock)",
      "available": true,
      "status": "CLOSED",
      "last_success": "2026-03-28T10:13:00Z",
      "resolution_m": 10,
      "latency_ms": 5
    }
  ]
}
```

---

### `GET /api/credits`
Check credit/quota usage across providers (no auth required).

**Request**:
```bash
curl http://localhost:8000/api/credits
```

**Response** (200 OK):
```json
{
  "organizations": [
    {
      "provider": "sentinel2",
      "organization": "Copernicus",
      "requests_this_month": 1250,
      "quota_monthly": 50000,
      "utilization_percent": 2.5
    },
    {
      "provider": "landsat",
      "organization": "USGS",
      "requests_this_month": 8900,
      "quota_monthly": 999999,
      "utilization_percent": 0.89
    }
  ]
}
```

---

## **Analysis**

### `POST /api/analyze`
Analyze an area of interest (AOI) for construction changes between two dates (auth required, rate-limited: 5/min).

**Request Headers**:
```
Authorization: Bearer <your-api-key>  (if API_KEY is set)
Content-Type: application/json
```

**Request Body**:
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [46.655, 24.710],
        [46.670, 24.710],
        [46.670, 24.720],
        [46.655, 24.720],
        [46.655, 24.710]
      ]
    ]
  },
  "start_date": "2026-02-27",
  "end_date": "2026-03-28",
  "provider": "auto",
  "confidence_threshold": 50,
  "async_execution": false
}
```

**Request Fields**:
- `geometry` (required): GeoJSON Polygon or MultiPolygon (must be valid geography)
- `start_date` (required): ISO 8601 date string (YYYY-MM-DD)
- `end_date` (required): ISO 8601 date string (YYYY-MM-DD)
- `provider` (optional, default: "auto"): "sentinel2" | "landsat" | "maxar" | "planet" | "demo" | "auto"
- `confidence_threshold` (optional, default: 50): 0–100, filter changes below threshold
- `async_execution` (optional, default: false): true to dispatch to background worker

**Response** (200 OK, sync):
```json
{
  "analysis_id": "ana-20260328-abc123",
  "status": "completed",
  "provider": "landsat",
  "is_demo": false,
  "area_km2": 1.234,
  "changes": [
    {
      "change_id": "chg-001",
      "change_type": "Excavation",
      "confidence": 87,
      "geometry": {
        "type": "Polygon",
        "coordinates": [[...]]
      },
      "centroid": { "lng": 46.6625, "lat": 24.715 },
      "rationale": [
        "NDVI decreased by 0.35 (vegetation loss)",
        "Cluster area: 5.2 hectares",
        "Sharp boundaries (machinery signature)"
      ]
    }
  ],
  "statistics": {
    "total_changes": 1,
    "average_confidence": 87,
    "min_confidence": 87,
    "max_confidence": 87,
    "total_affected_area_km2": 0.052
  },
  "scenes": {
    "before": {
      "scene_id": "S2A_20260227T053651_N0510",
      "date": "2026-02-27",
      "satellite": "Sentinel-2A",
      "cloud_percent": 12.5
    },
    "after": {
      "scene_id": "LC09_L2SP_161045_20260328_20260328_02_T1",
      "date": "2026-03-28",
      "satellite": "Landsat 9",
      "cloud_percent": 8.3
    }
  },
  "warnings": [],
  "execution_time_ms": 2350
}
```

**Response** (202 Accepted, async):
```json
{
  "job_id": "job-20260328-def456",
  "status": "pending",
  "analysis_id": null,
  "timestamp": "2026-03-28T10:15:00Z",
  "poll_url": "/api/jobs/job-20260328-def456"
}
```

**Error Responses**:

- **400 Bad Request**: Invalid geometry or date range
  ```json
  {
    "error": "invalid_request",
    "message": "end_date must be after start_date",
    "details": { "end_date": "2026-03-28", "start_date": "2026-03-28" }
  }
  ```

- **402 Payment Required**: Area exceeds max bounds
  ```json
  {
    "error": "area_exceeds_limit",
    "message": "AOI area (125.5 km²) exceeds maximum (100 km²)",
    "area_km2": 125.5,
    "max_area_km2": 100.0
  }
  ```

- **429 Too Many Requests**: Rate limit exceeded
  ```json
  {
    "error": "rate_limited",
    "message": "5 requests per 1 minute exceeded",
    "retry_after": 45
  }
  ```

- **503 Service Unavailable**: All providers down
  ```json
  {
    "error": "no_providers_available",
    "message": "No imagery providers available",
    "suggestions": ["Check network connectivity", "Try again in 1 minute"]
  }
  ```

---

### `POST /api/search`
Search for satellite imagery scenes without performing change detection (auth required, rate-limited: 10/min).

**Request Headers**:
```
Authorization: Bearer <your-api-key>
Content-Type: application/json
```

**Request Body**:
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[...]]
  },
  "start_date": "2026-02-27",
  "end_date": "2026-03-28",
  "provider": "auto",
  "cloud_threshold": 20,
  "max_results": 10
}
```

**Response** (200 OK):
```json
{
  "provider": "landsat",
  "geometry_bounds": { "north": 24.720, "south": 24.710, "east": 46.670, "west": 46.655 },
  "scenes": [
    {
      "scene_id": "LC09_L2SP_161045_20260328_20260328_02_T1",
      "date": "2026-03-28",
      "satellite": "Landsat 9",
      "cloud_percent": 8.3,
      "platform": "Landsat",
      "resolution_m": 30,
      "instrument": "OLI-2",
      "acquisition_time": "2026-03-28T05:35:00Z"
    },
    {
      "scene_id": "LC08_L2SP_160045_20260320_20260328_02_T1",
      "date": "2026-03-20",
      "satellite": "Landsat 8",
      "cloud_percent": 15.2,
      "platform": "Landsat",
      "resolution_m": 30,
      "instrument": "OLI",
      "acquisition_time": "2026-03-20T05:35:00Z"
    }
  ],
  "scene_count": 2,
  "search_time_ms": 1240
}
```

---

## **WebSocket — Live Job Progress**

### `WS /api/jobs/{job_id}/stream`
Real-time job state streaming via WebSocket. Replaces HTTP polling with server-push.

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8000/api/jobs/job-123/stream');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

**Server Messages**:

Progress update (sent on each state change):
```json
{ "type": "progress", "job_id": "job-123", "state": "started" }
```

Completion:
```json
{ "type": "completed", "job_id": "job-123", "state": "completed", "result": { ... } }
```

Failure:
```json
{ "type": "failed", "job_id": "job-123", "state": "failed", "error": "reason" }
```

Error (e.g., Celery not configured):
```json
{ "type": "error", "message": "Async jobs require Redis / Celery." }
```

**Notes**:
- Connection closes automatically on terminal states (completed, failed, cancelled).
- Frontend falls back to HTTP polling if WebSocket is unavailable.
- Requires Redis/Celery to be configured (otherwise sends error frame and closes).

---

## **Thumbnails**

### `GET /api/thumbnails/{scene_id}?key={cache_key}`
Serve a pre-generated satellite scene thumbnail as PNG.

**Request**:
```bash
curl http://localhost:8000/api/thumbnails/S2A_MSIL2A_20260315?key=abc123def456
```

**Response** (200 OK): PNG image bytes with `Content-Type: image/png`

**Response** (404 Not Found):
```json
{ "detail": "Thumbnail not found for scene 'S2A_MSIL2A_20260315'. It may have expired or was never generated." }
```

**Notes**:
- Thumbnails are generated during change detection and cached in-memory (LRU, max 128 entries).
- The `key` query parameter is returned by the analysis endpoint in `before_image` / `after_image` URLs.
- In demo mode, static PNG assets are used instead.

---

## **Async Jobs**

### `GET /api/jobs/{job_id}`
Check the status and result of an async analysis job (auth required).

**Request**:
```bash
curl -H "Authorization: Bearer your-api-key" http://localhost:8000/api/jobs/job-20260328-def456
```

**Response** (200 OK, pending):
```json
{
  "job_id": "job-20260328-def456",
  "status": "running",
  "progress_percent": 65,
  "created_at": "2026-03-28T10:15:00Z",
  "started_at": "2026-03-28T10:15:05Z",
  "updated_at": "2026-03-28T10:15:25Z",
  "result": null,
  "error": null,
  "cancel_url": "/api/jobs/job-20260328-def456/cancel"
}
```

**Response** (200 OK, completed):
```json
{
  "job_id": "job-20260328-def456",
  "status": "completed",
  "progress_percent": 100,
  "created_at": "2026-03-28T10:15:00Z",
  "started_at": "2026-03-28T10:15:05Z",
  "completed_at": "2026-03-28T10:17:30Z",
  "result": {
    "analysis_id": "ana-20260328-def456",
    "changes": [...],
    "statistics": {...}
  },
  "error": null
}
```

**Response** (200 OK, failed):
```json
{
  "job_id": "job-20260328-def456",
  "status": "failed",
  "progress_percent": 0,
  "created_at": "2026-03-28T10:15:00Z",
  "started_at": "2026-03-28T10:15:05Z",
  "failed_at": "2026-03-28T10:15:35Z",
  "result": null,
  "error": {
    "code": "provider_unavailable",
    "message": "All imagery providers unavailable"
  }
}
```

**Error Responses**:

- **404 Not Found**: Job does not exist
  ```json
  {
    "error": "job_not_found",
    "job_id": "job-20260328-unknown"
  }
  ```

---

### `DELETE /api/jobs/{job_id}/cancel`
Cancel an in-progress async analysis job (auth required).

**Request**:
```bash
curl -X DELETE -H "Authorization: Bearer your-api-key" \
  http://localhost:8000/api/jobs/job-20260328-def456/cancel
```

**Response** (200 OK):
```json
{
  "job_id": "job-20260328-def456",
  "status": "cancelled",
  "message": "Job cancelled successfully",
  "cancelled_at": "2026-03-28T10:16:00Z"
}
```

**Error Responses**:

- **409 Conflict**: Job already completed/failed
  ```json
  {
    "error": "job_not_cancellable",
    "message": "Job is already completed (status: completed)"
  }
  ```

---

## **Error Format**

All errors follow this structure:

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {
    "field": "additional context"
  }
}
```

**Common Error Codes**:
- `invalid_request`: Malformed request
- `unauthorized`: Missing/invalid API key
- `rate_limited`: Rate limit exceeded
- `area_exceeds_limit`: AOI too large
- `date_range_exceeded`: Date range > 365 days
- `no_providers_available`: All providers down
- `provider_unavailable`: Specific provider unavailable
- `unsupported_geometry`: Geometry type not supported (only Polygon/MultiPolygon)
- `internal_error`: Unexpected server error

---

## **Rate Limits**

Rate limits are per API key (or per IP if anonymous):

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /api/analyze` | 5 | 1 minute |
| `POST /api/search` | 10 | 1 minute |
| `GET/DELETE /api/jobs/*` | 20 | 1 minute |

**Rate Limit Headers**:
```
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 2
X-RateLimit-Reset: 1711607700
```

When limit exceeded: **429 Too Many Requests** with `Retry-After` header.

---

## **Authentication**

### API Key
If `API_KEY` is set in `.env`, include the key in all protected endpoints via one of three methods:

1. **Bearer token** (recommended):
```bash
curl -H "Authorization: Bearer your-api-key" http://localhost:8000/api/analyze
```

2. **Query parameter** (useful for WebSocket/browser testing):
```bash
curl "http://localhost:8000/api/analyze?api_key=your-api-key"
```

3. **Cookie**:
```bash
curl --cookie "api_key=your-api-key" http://localhost:8000/api/analyze
```

If `API_KEY` is empty, authentication is disabled (insecure dev mode).

### CORS
Allowed origins configured via `ALLOWED_ORIGINS` env (default: `http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000`).

---

## **Examples**

### Example 1: Analyze AOI (Sync)
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[46.655, 24.710], [46.670, 24.710], [46.670, 24.720], [46.655, 24.720], [46.655, 24.710]]]
    },
    "start_date": "2026-02-27",
    "end_date": "2026-03-28"
  }'
```

### Example 2: Analyze AOI (Async)
```bash
# Start job
JOB_ID=$(curl -s -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"geometry": {...}, "async_execution": true}' \
  | jq -r '.job_id')

# Poll status
curl http://localhost:8000/api/jobs/$JOB_ID

# Cancel if needed
curl -X DELETE http://localhost:8000/api/jobs/$JOB_ID/cancel
```

### Example 3: Search Imagery
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {...},
    "start_date": "2026-02-27",
    "end_date": "2026-03-28",
    "cloud_threshold": 20
  }'
```

---

## **Changelog**

### v3.0.0 (2026-03-28)
- Added commercial provider stubs: Maxar (SecureWatch) and Planet (PlanetScope/SkySat)
- Added WebSocket endpoint (`/api/jobs/{job_id}/stream`) for live job progress
- Added satellite thumbnail endpoint (`/api/thumbnails/{scene_id}`)
- Added PostgreSQL job persistence (optional, via `DATABASE_URL`)
- Redis-backed circuit breaker with in-process fallback
- Authentication via Bearer token, query param, or cookie (replaces `X-API-Key` header)
- `APP_MODE` supports `demo`, `staging`, `production` (replaces `live`)

### v2.0.0 (2026-03-28)
- Added async job management (`/api/jobs/*`)
- Added provider registry endpoint (`/api/providers`)
- Added credits/quota endpoint (`/api/credits`)
- Rate limiting on analyze (5/min), search (10/min), jobs (20/min)
- Improved error responses with structured codes

### v1.0.0 (2026-01-15)
- Initial release: sync analyze + health check
