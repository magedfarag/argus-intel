# Known Issues Register

This file captures the concrete issues already visible in the current workspace that should be treated as Phase 0 inputs.

## Frontend Issues

- `[x]` `frontend/src/components/GlobeView/GlobeView.tsx` fails typecheck because it expects `Chokepoint.bbox`, but the shared type exposes `geometry` and `centroid` — **RESOLVED**: uses `cp.geometry` and `cp.centroid.lon/lat` correctly; `tsc --noEmit` passes
- `[x]` `frontend/src/components/GlobeView/GlobeView.tsx` fails typecheck because it expects `DarkShipCandidate.last_known_position`, but the shared type exposes `last_known_lon` and `last_known_lat` — **RESOLVED**: uses `ds.last_known_lon` / `ds.last_known_lat`; `tsc --noEmit` passes
- `[~]` `frontend/src/components/GlobeView/GlobeView.tsx` has implicit `any` errors in multiple TripsLayer callbacks — **CLARIFIED**: suppressed with explicit `// eslint-disable-next-line @typescript-eslint/no-explicit-any`; intentional due to MapLibre/deck.gl type gaps; typecheck passes
- `[x]` `frontend/src/components/GlobeView/GlobeView.tsx` has an unused `baseStyle` prop path that should be removed or implemented

## Backend Issues

- `[x]` `app/workers/tasks.py` uses telemetry store calls that do not match the current `TelemetryStore` interface — **RESOLVED**: `store.upsert(ev)` replaced with `store.ingest_batch(events)` in `poll_rapidapi_ais` and `poll_vessel_data`
- `[x]` poller tasks normalize data but do not clearly feed the same replay path the frontend consumes — **RESOLVED (Phase 1 Track B, 2026-04-04)**: GDELT/OpenSky/AIS/RapidAPI-AIS/VesselData pollers now call `get_default_event_store().ingest_batch(events)` alongside TelemetryStore writes; `provenance.raw_source_ref` is entity-specific for all connectors
- `[ ]` `src/api/playback.py` currently splits behavior across `EventStore` and `TelemetryStore`, which complicates a unified replay model — **Phase 1 Track C scope**: `query_playback()` → EventStore; `get_entity_track()` → TelemetryStore; unification is a Phase 1 contract freeze deliverable

## Planning Risks

- `[ ]` adding new operational layers before Phase 0 closes will multiply contract churn
- `[ ]` starting a renderer migration before Phase 1 and Phase 2 contracts stabilize will increase re-porting cost
- `[ ]` adding simulated sensor modes before provenance rules are defined will blur the line between real and synthetic views

## Validation Notes

- Frontend local TypeScript build was failing at the time this planning pack was created — **NOW PASSING** (2026-04-04): `npx tsc --noEmit` exits clean
- Targeted backend tests for playback, AIS, and OpenSky were passing at the time this planning pack was created — **852 unit tests pass** as of 2026-04-04; CI now includes frontend typecheck job
- `tests/unit/test_cache.py`: `is_healthy()` tests updated to match documented design intent (memory fallback = degraded = `False`)
- `tests/unit/test_telemetry_store.py`: interface contract tests added asserting `ingest()`/`ingest_batch()` exist and `upsert()` does not

## Usage

- Use this file during sprint planning for Phase 0.
- Move items out of this file once they have a permanent home in tests, docs, or resolved code.

## Phase 2 Notes (2026-04-04)

### What was implemented

Tracks A–E of Phase 2 are **complete**:

- **Models** (`src/models/operational_layers.py`): 7 Pydantic v2 models — `SatelliteOrbit`, `SatellitePass`, `AirspaceRestriction`, `NotamEvent`, `GpsJammingEvent`, `StrikeEvent`, `EvidenceLink`. All require UTC-aware datetimes; confidence bounds enforced at model level.
- **Connectors** (all stubs, no live HTTP calls):
  - `OrbitConnector` — TLE text parser + flat-earth pass prediction
  - `AirspaceConnector` — 5 seed restrictions + 3 NOTAMs; `is_active()` uses real-time UTC comparison
  - `JammingConnector` — 3–5 deterministic events seeded from window hash; reproducible
  - `StrikeConnector` — 4–6 deterministic strike events; idempotent `add_evidence()` with dedup
- **Routers** registered in `app/main.py`:
  - `/api/v1/orbits`, `/api/v1/airspace`, `/api/v1/jamming`, `/api/v1/strikes`
- **Frontend**: TypeScript types, API clients, React hooks, `OperationalLayersPanel`, and `useTimelineSync` hook — compiles clean (`tsc --noEmit` zero errors).
- **Tests**: 186 new tests (65 model-level, 58 connector-level, 30 integration HTTP, 33 E2E mixed-layer replay) — all pass. Full suite: 1119 passed, 11 skipped, 0 failures.

### Known limitations of stub connectors

- **No live data**: all connectors return deterministic synthetic data. To activate real ingestion, replace the stub logic in each `fetch()` / `detect_*` / `fetch_*` method with live API calls.
- **In-memory stores only**: the API routers store seeded records in module-level Python dicts. Data is lost on process restart. No database persistence for these tables yet.
- **Pass prediction model**: `OrbitConnector.compute_passes()` uses a simplified periodic flat-earth model. For production accuracy, replace with a proper SGP4/SDP4 propagator (e.g., `sgp4` library).
- **Orbit pass geo-targeting approximation**: pass windows are computed relative to a fixed observer lon/lat passed as query parameters. The connector uses a flat-earth periodic approximation rather than true orbital mechanics; results are directionally correct but not geodetically precise. For AOI-based targeting, the caller should pass the AOI centroid as the observer coordinates.
- **Area calculations**: jamming circle polygons use flat-earth approximation — adequate for demo, not for geodetic mission planning.
- **Rendering deferred**: map/globe rendering of the new layers (orbit tracks, airspace polygons, jamming heat, strike markers) is captured as frontend state in `OperationalLayersPanel` and `useTimelineSync` but is not visually rendered on the 2D/3D views yet — deferred to the 3D world sprint (Phase 3).

### Operational risks

- The `EvidenceLink` + `corroboration_count` workflow is designed for multi-source fusion but is currently single-user in-memory only. A persistence layer is needed before this is usable in production investigations.
