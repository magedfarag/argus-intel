# Phase 2 — Operational Layers

## Objective

Add the missing article-parity operational layers on top of the unified timeline.

## Exit criteria

- orbit/pass, airspace/no-fly, strike, and jamming layers exist
- each new layer is replayable and time-aligned with existing feeds
- analysts can toggle these layers in both 2D and globe views

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P2-1 | Implement orbit/pass source adapter | `src/connectors/`, `src/models/` | `L2` | `[ ]` | P1-1, P1-3 | `P2-A` | Public TLE/NORAD-style source; normalize to orbit/pass events |
| P2-2 | Implement airspace/no-fly source adapter | `src/connectors/`, `src/models/` | `L2` | `[ ]` | P1-1, P1-3 | `P2-B` | NOTAM/restriction polygons with start/end time |
| P2-3 | Implement strike-event source adapter | `src/connectors/`, `src/models/` | `L2` | `[ ]` | P1-1, P1-3 | `P2-C` | Normalize coordinates, confidence, provenance |
| P2-4 | Implement GPS jamming analytics from existing flight tracks | `src/services/`, `src/api/` | `L3` | `[ ]` | P1-4 | `P2-C` | Derived layer built from persisted telemetry confidence gaps |
| P2-5 | Add query APIs and filter controls for all new layers | `src/api/`, `frontend/src/api/`, `frontend/src/components/` | `L3` + `L4` | `[ ]` | P2-1, P2-2, P2-3, P2-4 | `P2-D` | Unified layer/timeline filtering |
| P2-6 | Add 2D map rendering, legend, and playback sync | `frontend/src/components/Map/`, timeline controls | `L4` | `[ ]` | P2-5 | `P2-D` | Keep density limits and performance caps explicit |
| P2-7 | Add globe rendering for new layers | current globe or interim 3D surface | `L5` | `[ ]` | P2-5 | `P2-D` | This is temporary until Phase 3 replaces the renderer |
| P2-8 | Add alerting rules and evidence hooks for new event types | `src/services/`, `frontend/src/components/` | `L3` + `L4` | `[ ]` | P2-5 | `P2-D` | Rule-based alerts first, not LLM-driven |

## Parallel execution notes

- `P2-1`, `P2-2`, and `P2-3` are clean parallel ingestion lanes.
- `P2-4` can begin once persisted telemetry query patterns are stable.
- `P2-6` and `P2-7` should consume shared fixtures from `P2-5`.

## Validation

- all new layers replay correctly over the same time window
- no UI layer can drift outside the main UTC playhead
- provenance is visible for derived jamming events

## Gate review

- [ ] Orbit/pass layer works
- [ ] Airspace/no-fly layer works
- [ ] Strike layer works
- [ ] Jamming layer works
- [ ] All new layers are time-aligned in playback
