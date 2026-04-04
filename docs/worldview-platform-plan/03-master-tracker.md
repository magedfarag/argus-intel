# Master Tracker

## Program status

Current state: planning complete, execution not started.

## Phase tracker

| Phase | Name | Duration | Primary outcome | Status | Gate |
|---|---|---|---|---|---|
| 0 | Stabilization | 1 sprint | build-clean, data-consistent current branch | `[ ]` | build + smoke green |
| 1 | Historical data plane | 2 sprints | unified storage, ingestion, replay | `[ ]` | persisted 24h/7d/30d replay |
| 2 | Operational layers | 2 sprints | orbit, airspace, strike, jamming layers | `[ ]` | unified timeline parity |
| 3 | 3D world | 3 sprints | realistic 3D scene with ported overlays | `[ ]` | 3D inspection usable |
| 4 | Sensor fusion | 3 sprints | render modes and camera/video sync | `[ ]` | cross-view playback works |
| 5 | Investigation workflows | 2 sprints | cases, evidence, alerts, LLM assist | `[ ]` | analyst workflow complete |
| 6 | Hardening | 2 sprints | auth, perf, governance, readiness | `[ ]` | pilot/production ready |

## Immediate priority stack

1. Phase 0 task `P0-1`: fix current frontend and worker regressions.
2. Phase 0 task `P0-2`: choose the single event/replay storage contract.
3. Phase 1 task `P1-1`: freeze schema extensions needed by later phases.

## Known blockers at plan creation

- `frontend/src/components/GlobeView/GlobeView.tsx` does not typecheck cleanly.
- `app/workers/tasks.py` and `src/api/playback.py` use split ingestion/query paths.
- The current replay model depends heavily on demo-seeded data.

## Critical path

```text
P0-2 shared storage contract
    ->
P1-1 event model extensions
    ->
P1-3 unified ingestion pipeline
    ->
P1-5 persisted replay windows
    ->
P2 operational source layers
    ->
P3 3D scene migration
    ->
P4 sensor/video sync
    ->
P5 investigation workflows
    ->
P6 hardening
```

## Phase gate checklist

- Phase 0 gate: frontend typecheck, targeted pytest, startup smoke, plan/contracts frozen
- Phase 1 gate: persisted replay from live or fixture-backed stored data
- Phase 2 gate: new event families visible and replayable in one timeline
- Phase 3 gate: analysts can inspect incidents in a true 3D scene
- Phase 4 gate: sensor/video views stay synchronized with the timeline
- Phase 5 gate: saved investigations and evidence packs are operational
- Phase 6 gate: auth, perf, retention, and runbooks validated

## Update rule

Only the active phase file should be updated day-to-day. This file should change only when:

- a phase starts
- a phase completes
- the critical path changes
- a blocker changes the release cutline
