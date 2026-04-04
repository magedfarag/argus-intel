# ARGUS — Multi-Domain Surveillance Intelligence — Guidelines

## Architecture

Single FastAPI service (`app/main.py`) that:
- Serves the static frontend from `app/static/`
- Exposes `GET /api/health`, `GET /api/config`, `POST /api/analyze`
- Returns curated deterministic results — **no live imagery**

Provider stubs live in `app/providers/`. Each extends `SatelliteProvider` and implements `search_imagery()`. The demo ignores them; they document the real integration contract.

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) and [docs/API.md](../docs/API.md) for full details.

## Build and Run

```bash
# Install
pip install -r requirements.txt

# Run (auto-reload)
uvicorn app.main:app --reload
```

Windows shortcut: `run_demo.bat` (creates `.venv`, installs, starts server).

No build step for the frontend — all static files are served as-is.

## Conventions

- All Python files use `from __future__ import annotations`.
- Request/response models use **Pydantic v2** (`model_validator(mode='after')`).
- `TODAY = date(2026, 3, 28)` is hardcoded in `main.py`; the demo's 30-day window is relative to it.
- Curated detection scenarios are defined in the `SCENARIOS` list in `main.py`. Add or modify entries there to change demo output.
- Frontend is vanilla JS + Leaflet + Turf.js — no transpilation, no bundler.

## Key Extension Points

| Intent | Where to edit |
|--------|--------------|
| Real imagery search | `Sentinel2StacProvider.search_scenes()` / `LandsatStacProvider.search_scenes()` in `providers.py` |
| Change detection scenarios | `SCENARIOS` list in `main.py` |
| API shape | `AnalyzeRequest` / `AnalyzeResponse` / `ChangeRecord` models in `main.py` |
| Frontend map behaviour | `backend/app/static/app.js` |

## Pitfalls

- There are **no tests**. Add a `tests/` directory when introducing new logic.
- Do not hardcode new dates or time windows independent of `TODAY`; keep temporal logic relative to it.
- Area calculation in `_polygon_area_km2()` uses a flat-earth approximation — sufficient for a demo, not for production.
- Circle selections are converted to 64-step polygons client-side before the geometry is posted; the backend only accepts `Polygon` / `MultiPolygon`.
