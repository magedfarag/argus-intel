# ARGUS

**Production-ready FastAPI + React intelligence platform for AOI-based monitoring across imagery, telemetry, contextual events, and analyst workflows.**

ARGUS combines satellite imagery analysis, real-time event streams, and operational intelligence into a unified platform. The current codebase integrates V1 change-detection with V2 operational APIs, plus Celery background processing, RBAC, audit logging, and multi-source connector health monitoring.

## Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, Celery, Redis, SQLAlchemy/Alembic, rasterio
- **Frontend**: React 18, TypeScript, Vite, MapLibre GL JS, deck.gl, TanStack Query
- **Data Sources**: Sentinel-2, Landsat, Earth Search, Planetary Computer, GDELT, OpenSky, AISStream, USGS, NASA, NOAA, OpenAQ, NGA MSI, OSM

## Quick Start

### One-Command Demo (Windows)

The fastest way to get started:

```cmd
run_demo.bat
```

This script will:
- Create a Python virtual environment (`.venv/`)
- Install all dependencies
- Start the FastAPI backend with hot reload
- Open your browser to the API docs

Visit:
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/health`

### Manual Setup

#### Backend Only

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Full Stack (Backend + Frontend + Infrastructure)

```powershell
# 1. Start infrastructure (Redis, PostgreSQL, etc.)
.\tools\start_infra.ps1

# 2. Start backend API
.\tools\run_api.ps1

# 3. Start Celery worker (background jobs)
.\tools\run_worker.ps1

# 4. (Optional) Start Celery beat scheduler
.\tools\run_beat.ps1

# 5. Start frontend dev server
cd frontend
npm install
npm run dev
```

Visit:
- React UI: `http://localhost:5173`
- Backend API: `http://localhost:8000/docs`

### Docker Compose

For a complete containerized environment:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

**Note**: The Compose file starts backend services and infrastructure but NOT the Vite frontend. Run the React app separately for browser UI access.

## Project Structure

```
argus-intel/
├── run_demo.bat                 # ONE-COMMAND QUICK START (Windows)
├── app/                         # Legacy FastAPI backend (V1)
│   ├── cache/                   # Query caching layer
│   ├── models/                  # Pydantic request/response models
│   ├── providers/               # Satellite imagery provider stubs
│   ├── routers/                 # API route handlers
│   ├── services/                # Business logic services
│   └── workers/                 # Celery background workers
├── src/                         # Core V2 platform (canonical models, services)
│   ├── api/                     # V2 FastAPI endpoints
│   ├── connectors/              # External data source connectors
│   ├── models/                  # Canonical event models
│   ├── services/                # Core business logic
│   └── storage/                 # Database models and persistence
├── frontend/                    # React + TypeScript operational UI
│   ├── src/                     # React application source
│   │   ├── components/          # React components
│   │   ├── services/            # Frontend services
│   │   └── ...
│   └── e2e/                     # Playwright end-to-end tests
├── docs/                        # All project documentation
│   ├── getting-started/         # Setup and onboarding guides
│   ├── delivery/                # Delivery and release documentation
│   └── ...
├── tools/                       # Operational scripts and utilities
│   ├── run_api.ps1              # Start FastAPI backend
│   ├── run_worker.ps1           # Start Celery worker
│   ├── start_infra.ps1          # Start Docker infrastructure
│   ├── run-e2e-tests.ps1        # Run E2E tests
│   └── ...
└── tests/                       # Test suite
    ├── fixtures/                # Test data fixtures
    ├── unit/                    # Unit tests
    └── integration/             # Integration tests
```

## Runtime Modes

ARGUS supports three runtime modes to accommodate different deployment scenarios:

| `APP_MODE` | Behavior | Use Case |
|---|---|---|
| `demo` | Demo provider only, seeded synthetic data, auth bypass | Demos, presentations, testing |
| `staging` | Real providers with demo fallback | Development, staging environments |
| `production` | Real providers only, no fallback | Production deployments |

**Security Note**: If `API_KEY` is unset outside demo mode, the app runs in an insecure developer-friendly bypass mode. Always set `API_KEY` in production.

See [docs/reference/environment.md](docs/reference/environment.md) for all configuration options.

## Available Tools

All operational scripts live in the `tools/` directory:

| Script | Purpose |
|--------|---------|
| `run_api.ps1` | Start FastAPI backend with hot reload |
| `run_worker.ps1` | Start Celery worker for background jobs |
| `run_beat.ps1` | Start Celery beat scheduler for periodic tasks |
| `start_infra.ps1` | Start Docker infrastructure (Redis, PostgreSQL) |
| `run-e2e-tests.ps1` | Run Playwright E2E tests |
| `debug_stac.py` | Debug STAC API connectivity |
| `status_check.py` | Check service health |
| `verify_data_sources.py` | Verify external data source connectivity |

## Testing

```powershell
# Backend unit tests
pytest tests/unit -v

# Backend integration tests
pytest tests/integration -v

# Frontend E2E tests
.\tools\run-e2e-tests.ps1

# Test coverage
pytest --cov=app --cov=src tests/
```

See [docs/testing/strategy.md](docs/testing/strategy.md) for comprehensive testing guidance.

## Documentation

Start with [docs/README.md](docs/README.md). The key current docs are:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/API.md](docs/API.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md)
- [docs/getting-started/local-development.md](docs/getting-started/local-development.md)
- [docs/reference/environment.md](docs/reference/environment.md)
- [docs/testing/strategy.md](docs/testing/strategy.md)

Delivery reports, handover material, and validation snapshots live under [docs/delivery](docs/delivery/README.md).

