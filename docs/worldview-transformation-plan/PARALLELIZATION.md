# Parallelization And Subagent Lanes

This file defines the recommended parallel work split for engineers or subagents.

## Delegation Rules

- Keep one integration owner on the main thread.
- Delegate bounded tracks with disjoint write scopes.
- Do not let subagents independently redefine shared contracts.
- Treat schema, API types, and renderer decisions as integration-owned freeze points.

## Recommended Standing Lanes

### Lane A: Schema, Storage, And Ingestion

Focus:

- canonical event extensions
- persistence models
- raw payload capture
- normalization and provenance

Primary write scope:

- `src/models/`
- `src/storage/`
- `src/connectors/`
- `src/services/` for ingestion services

### Lane B: Playback, Query, And Timeline Contracts

Focus:

- historical query APIs
- playback materialization
- event and telemetry unification
- timeline synchronization contracts

Primary write scope:

- `src/api/playback.py`
- `src/services/playback_service.py`
- `src/services/event_store.py`
- `src/services/telemetry_store.py`
- `frontend/src/hooks/`
- `frontend/src/api/`

### Lane C: Operational Connectors And Layers

Focus:

- orbit/pass sources
- airspace and NOTAM sources
- jamming derived analytics
- strike/event marker sources

Primary write scope:

- `src/connectors/`
- `src/api/`
- `frontend/src/components/Map/`
- `frontend/src/components/GlobeView/`
- `frontend/src/components/TimelinePanel/`

### Lane D: 3D Renderer And Scene Integration

Focus:

- renderer evaluation
- scene graph integration
- terrain/buildings
- overlay porting
- camera and navigation

Primary write scope:

- `frontend/src/components/GlobeView/`
- new 3D scene components
- renderer-specific adapters

### Lane E: Investigation And Evidence Workflows

Focus:

- saved investigations
- watchlists
- briefing workflows
- evidence packs
- narrative exports

Primary write scope:

- `src/api/`
- `src/services/`
- `frontend/src/components/`
- export/reporting code

### Lane F: Hardening And Platform Operations

Focus:

- auth
- RBAC
- audit
- CI
- performance
- rollout and runbooks

Primary write scope:

- `app/`
- auth middleware and config
- `.github/`
- operational docs

## Parallelization By Phase

### Phase 0

- Lane A not needed beyond small store fixes.
- Lane B and Lane C can work in parallel on replay/store cleanup and overlay type fixes.
- Lane F can add CI gates in parallel.

### Phase 1

- Lane A and Lane B run in parallel first.
- Lane C waits for schema and query contract freeze.

### Phase 2

- Lane C splits cleanly into orbit, airspace, jamming, and strike streams after schema freeze.
- Lane B supports timeline integration in parallel.

### Phase 3

- Lane D leads.
- Lane C supports overlay inventory and porting.

### Phase 4

- Lane D handles render modes.
- Lane C or E can handle camera abstractions and detection overlays.

### Phase 5

- Lane E leads.
- Lane B supports replay-backed investigation queries.

### Phase 6

- Lane F leads.
- All other lanes supply hardening fixes inside their owned surfaces.

## Review Cadence

- Daily: contract changes and blockers
- Per sprint: phase file status refresh
- Per milestone: update `README.md`, `MILESTONES.md`, and `DEPENDENCIES.md`
