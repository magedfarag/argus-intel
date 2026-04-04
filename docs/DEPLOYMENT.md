# Deployment Guide

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
