# Workstreams And Subagents

This plan assumes work can run in parallel, but only inside clear contracts. Each lane should have a single owner or subagent and a tight file boundary.

## Lane map

| Lane | Purpose | Primary areas |
|---|---|---|
| `L0 Integrator` | freeze contracts, merge cross-lane work, keep CI green | `src/models/`, `frontend/src/api/`, CI, plan updates |
| `L1 Data Platform` | storage, schemas, migrations, retention, snapshot structure | `src/storage/`, `alembic/`, object storage layout |
| `L2 Ingestion` | connectors, polling, normalization, raw payload capture | `src/connectors/`, `app/workers/tasks.py`, `src/normalization/` |
| `L3 Query + Playback` | event query APIs, playback, materialization, derived analytics | `src/api/`, `src/services/` |
| `L4 Frontend Ops` | 2D map, timeline, panels, typed clients | `frontend/src/App.tsx`, `frontend/src/components/`, `frontend/src/hooks/` |
| `L5 Frontend 3D + Sensor` | 3D renderer, camera views, render modes, heavy overlays | `frontend/src/components/GlobeView/`, future 3D scene modules |
| `L6 QA + Ops` | tests, perf, observability, load, runbooks | `tests/`, `.github/`, `docs/`, dashboards |

## Subagent rules

- `L0 Integrator` owns schema and API contract changes.
- `L2 Ingestion` does not invent event shapes independently; it implements contracts frozen by `L0`.
- `L4 Frontend Ops` consumes typed API contracts only after `L0` and `L3` publish them.
- `L5 Frontend 3D + Sensor` should work against stable fixtures until real APIs are ready.
- `L6 QA + Ops` blocks phase completion if required gates are missing.

## Handoff requirements

Every cross-lane change must ship with:

- updated Pydantic model or schema
- updated frontend TypeScript type
- at least one test fixture or smoke test
- plan status update in the active phase file

## Parallelization model by phase

### Phase 0

- `P0-A`: frontend build/type cleanup
- `P0-B`: ingestion/playback store cleanup
- `P0-C`: CI and validation gates
- `P0-D`: architecture contract freeze for Phase 1

### Phase 1

- `P1-A`: storage schema and snapshot persistence
- `P1-B`: connector write-path unification
- `P1-C`: playback/materialization query layer
- `P1-D`: frontend replay integration against persisted data

### Phase 2

- `P2-A`: orbit/pass sources
- `P2-B`: airspace/no-fly sources
- `P2-C`: strike/jamming models and analytics
- `P2-D`: layer controls, timeline rendering, alerts

### Phase 3

- `P3-A`: 3D stack ADR and bootstrap
- `P3-B`: terrain/building data integration
- `P3-C`: overlay port and selection tooling
- `P3-D`: performance budget and render validation

### Phase 4

- `P4-A`: render mode framework
- `P4-B`: camera/video source abstraction
- `P4-C`: synchronized playback across scene + video
- `P4-D`: object/detection overlay UX

### Phase 5

- `P5-A`: investigation domain models and APIs
- `P5-B`: evidence/alert/watchlist flows
- `P5-C`: LLM-assisted briefing/query layer
- `P5-D`: analyst workflow QA and red-team review

### Phase 6

- `P6-A`: auth, RBAC, audit
- `P6-B`: caching/materialization/performance
- `P6-C`: retention, cost, and provider governance
- `P6-D`: runbooks, operational readiness, rollback

## Merge discipline

- Never merge a lane that breaks `tsc`, pytest, or startup smoke.
- Prefer fixtures over speculative live integrations until the contract is frozen.
- Re-open plan items when the implementation regresses, even if an older plan marked them complete.
