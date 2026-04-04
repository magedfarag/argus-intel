# WorldView Transformation Plan

This folder is the master planning pack for transforming the current ARGUS codebase from a map-and-globe surveillance demo into a replayable multi-sensor operational platform inspired by the referenced articles.

This index is the entry point and the single document that points to every planning artifact in this folder.

## Planning Principles

- Stabilize the current branch before adding net-new complexity.
- Make every visible layer replayable from a single historical data plane.
- Land features in client-visible phases, each with clear exit criteria.
- Split work into subagent-safe lanes with disjoint write scopes wherever possible.
- Prefer repo-aligned incremental delivery over greenfield redesign.

## Status Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[!]` Blocked
- `[-]` Deferred

## Recommended Delivery Sequence

1. `[x]` [Phase 0: Stabilize Current Branch](./PHASE_0_STABILIZE_CURRENT_BRANCH.md)
2. `[x]` [Phase 1: Unified Historical Data Plane](./PHASE_1_UNIFIED_DATA_PLANE.md)
3. `[x]` [Phase 2: Article-Parity Operational Layers](./PHASE_2_OPERATIONAL_LAYERS.md)
4. `[x]` [Phase 3: 3D World Upgrade](./PHASE_3_3D_WORLD.md)
5. `[x]` [Phase 4: Sensor Fusion And Simulator Modes](./PHASE_4_SENSOR_FUSION.md)
6. `[x]` [Phase 5: Investigation Workflows](./PHASE_5_INVESTIGATIONS.md)
7. `[x]` [Phase 6: Hardening And Release](./PHASE_6_HARDENING.md)

## Companion Documents

- [Milestones](./MILESTONES.md)
- [Dependencies And Critical Path](./DEPENDENCIES.md)
- [Parallelization And Subagent Lanes](./PARALLELIZATION.md)
- [Known Issues Register](./KNOWN_ISSUES.md)

## Current Assessment

The current workspace already has:

- 2D and 3D views
- imagery, events, GDELT, ship, and aircraft layers
- playback endpoints and a timeline UI
- maritime/chokepoint/dark-ship/intel briefing work

The current workspace still lacks:

- a unified durable replay model across all live feeds
- article-specific layers such as orbits, airspace, jamming, and strike reconstruction
- a true 3D world renderer with terrain/buildings
- sensor simulation modes such as thermal and night vision
- georegistered video/camera fusion
- production-grade auth, audit, and operational release controls

## Phase Gate Rules

- Do not start Phase 2 feature expansion until Phase 0 and Phase 1 exit criteria are met.
- Phase 3 evaluation can begin early, but renderer lock-in must not block Phase 2 backend work.
- Phase 4 depends on a stable 3D scene foundation from Phase 3.
- Phase 5 can begin in slices after Phase 1 is stable, but evidence and narrative workflows should not bypass the unified data plane.
- Phase 6 is the final release gate and should consolidate auth, performance, observability, and rollout readiness.

## Ownership Model

- One lead owner maintains this index and updates cross-phase status.
- Each phase file has track-level work packages that can be assigned to separate engineers or subagents.
- Cross-cutting decisions that change contracts must be reflected in `DEPENDENCIES.md` and `PARALLELIZATION.md`.

## First Recommended Execution Slice

If the team starts today, begin with:

1. Phase 0 Track A: frontend stabilization
2. Phase 0 Track B: ingestion/store stabilization
3. Phase 0 Track C: CI and quality gates

These three tracks are parallel-safe and remove the biggest current execution risk.
