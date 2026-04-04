# Dependencies And Critical Path

This file captures the sequencing rules across phases and the key blockers that should shape staffing and subagent delegation.

## Critical Path

1. Stabilize the current branch
2. Unify the historical data plane
3. Add article-parity operational layers
4. Lock the 3D renderer and scene foundation
5. Add sensor fusion and simulator modes
6. Layer on investigation workflows
7. Harden for release

## Cross-Phase Dependencies

### Phase 0 -> Phase 1

- Phase 1 must inherit a build-clean frontend and consistent backend stores.
- Schema and replay work should not start on top of known broken overlays or dead-end ingestion paths.

### Phase 1 -> Phase 2

- Phase 2 event families require a stable canonical contract and one persistent replay path.
- New operational connectors should target the unified event model, not ad hoc side stores.

### Phase 1 -> Phase 3

- Phase 3 renderer evaluation can start early.
- Full renderer migration should wait until the data model for new layers is stable enough to port once.

### Phase 2 -> Phase 3

- Phase 3 should ingest the finished layer contract for orbits, airspace, jamming, and strikes.
- Avoid porting placeholder data structures that will be changed again in Phase 2.

### Phase 3 -> Phase 4

- Simulator render modes depend on a stable scene graph and camera model.
- Video/camera georegistration depends on the 3D scene coordinate system.

### Phase 1/3/4 -> Phase 5

- Investigations depend on durable event history from Phase 1.
- Evidence views depend on 3D and sensor assets from Phases 3 and 4 where relevant.

### All Earlier Phases -> Phase 6

- Hardening should consolidate actual implemented systems.
- Do not front-load enterprise governance before the core experience exists.

## Contract Freeze Points

- Freeze 1: canonical event extensions for new operational layers before Phase 2 UI fan-out.
- Freeze 2: query and playback contract before Phase 2 timeline synchronization work.
- Freeze 3: renderer choice before broad scene porting in Phase 3.
- Freeze 4: camera/video abstraction before Phase 4 multi-view sync.

## Current Known Blockers

- `frontend/src/components/GlobeView/GlobeView.tsx` expects fields that do not match current shared types.
- `app/workers/tasks.py` contains telemetry ingestion paths that are inconsistent with `TelemetryStore`.
- `src/api/playback.py` currently splits `EventStore` and `TelemetryStore` responsibilities in ways that make replay harder to reason about.

## Dependency Risk Rules

- Any task that changes event contracts must update API types and the affected phase file before implementation starts.
- Any task that introduces a new store or persistence path must explain why the unified data plane is not sufficient.
- Any UI-only proof of concept that bypasses the replay model is considered disposable unless explicitly marked as spike work.
