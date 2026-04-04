# WorldView Platform Plan

This folder tracks the execution plan for evolving ARGUS from its current AOI-first operational map into a replayable, article-inspired multi-sensor intelligence platform.

The plan is intentionally:

- phase-gated
- trackable with checklist status markers
- split into small files instead of one monolith
- structured for parallel subagent execution with explicit lane ownership
- biased toward data-plane and replay correctness before visual spectacle

## Design priorities

- one shared historical timeline for all feeds
- durable snapshots for volatile data sources
- thin vertical slices with visible analyst value at the end of each phase
- contract-first parallel work between backend, frontend, and visualization lanes
- no premature 3D/video overbuild before data integrity and replay are stable

## Tracking legend

| Symbol | Meaning |
|---|---|
| `[ ]` | Not started |
| `[~]` | In progress |
| `[x]` | Complete |
| `[!]` | Blocked |
| `[-]` | Deferred |

## What is in this package

- `01-program-overview.md` — scope, non-goals, success metrics, release cutlines
- `02-workstreams-and-subagents.md` — parallel execution lanes, subagent boundaries, handoff rules
- `03-master-tracker.md` — top-level status, critical path, phase gates, immediate priorities
- `10-phase-0-stabilization.md` — stabilize the current branch and make the stack build-clean
- `20-phase-1-historical-data-plane.md` — unified storage, ingestion, replay, and snapshot pipeline
- `30-phase-2-operational-layers.md` — orbit, airspace, strike, and jamming layers
- `40-phase-3-3d-world.md` — 3D scene migration and overlay port
- `50-phase-4-sensor-fusion.md` — render modes, camera/video abstraction, and cross-view sync
- `60-phase-5-investigation-workflows.md` — investigation UX, alerts, evidence, and LLM assistance
- `70-phase-6-hardening.md` — auth, performance, caching, retention, and operational readiness

## Reading order

1. `01-program-overview.md`
2. `02-workstreams-and-subagents.md`
3. `03-master-tracker.md`
4. current active phase file only

## Recommended next step

After approving this plan, start **Phase 0 only**:

1. fix the current branch regressions
2. unify the ingestion/query architecture
3. lock subagent lane boundaries
4. do not begin Cesium/video/sensor-mode work before the Phase 1 gate passes

## Related repository baselines

- `docs/geoint-platform-architecture-and-plan/README.md`
- `docs/geoint-platform-architecture-and-plan/plan/V2_IMPLEMENTATION_PLAN.md`
- `MARITIME_PLAN.md`

## Notes

This package is execution-first. It is meant to be updated as work moves, not archived as a static proposal.
