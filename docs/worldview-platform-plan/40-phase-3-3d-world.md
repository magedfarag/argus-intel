# Phase 3 — 3D World

## Objective

Replace the current stylized globe with a true 3D inspection surface.

## Exit criteria

- 3D stack decision is locked
- terrain and building context are available in the scene
- core overlays are ported and inspectable in 3D
- render performance is acceptable on target pilot hardware

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P3-1 | Write ADR for the 3D stack choice | docs + renderer bootstrap | `L0` + `L5` | `[ ]` | P2 gate | `P3-A` | CesiumJS vs another 3D Tiles-capable path; freeze before major code |
| P3-2 | Bootstrap the selected 3D scene framework | `frontend/src/components/` | `L5` | `[ ]` | P3-1 | `P3-A` | Establish scene shell, camera, base layers |
| P3-3 | Integrate terrain and building datasets | scene data adapters | `L5` | `[ ]` | P3-2 | `P3-B` | Bound scope to pilot AOIs first |
| P3-4 | Port AOI, event, imagery, ship, aircraft, and Phase 2 layers into the new scene | scene overlays + shared adapters | `L5` + `L4` | `[ ]` | P3-2, P3-3 | `P3-C` | Reuse shared typed sources where possible |
| P3-5 | Add selection, inspection, and line-of-sight tools | scene interaction modules | `L5` | `[ ]` | P3-4 | `P3-C` | Focus on analyst utility, not cinematic movement |
| P3-6 | Add performance budgets, fixture scenes, and regression tests | `tests/`, perf harness | `L6` | `[ ]` | P3-2, P3-4 | `P3-D` | FPS, load time, memory budget on pilot AOIs |

## Parallel execution notes

- `P3-2` and `P3-6` can start together once `P3-1` is approved.
- `P3-4` should use shared scene adapter contracts so overlays are not rewritten per layer.

## Validation

- analysts can inspect at least one pilot incident in 3D
- layer selection remains consistent with 2D and timeline views
- scene performance stays within agreed bounds

## Gate review

- [ ] 3D stack choice is frozen
- [ ] Terrain/building context is usable
- [ ] Core overlays are ported
- [ ] Performance budget is met on pilot AOIs
