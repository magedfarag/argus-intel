# Phase 4 — Sensor Fusion

## Objective

Add sensor-mode rendering and camera/video abstractions on top of the 3D scene.

## Exit criteria

- render modes exist and are time-synchronized
- camera/video sources can be registered and replayed
- users can follow the same event across scene, map, and video views

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P4-1 | Build render-mode framework for day, low-light, thermal, and simplified CRT views | scene renderer + shaders | `L5` | `[ ]` | P3 gate | `P4-A` | Start with bounded visual modes, not full photorealistic simulation |
| P4-2 | Define camera/video event and source model | `src/models/`, `frontend/src/api/` | `L0` + `L1` | `[ ]` | P1-1 | `P4-B` | Georegistered source, playback window, provenance, media refs |
| P4-3 | Implement camera/video registry and playback APIs | `src/api/`, `src/services/` | `L3` | `[ ]` | P4-2 | `P4-B` | Fixture-backed initially, live sources later |
| P4-4 | Build video/camera panel and time-sync controls | frontend panels + timeline | `L4` | `[ ]` | P4-3 | `P4-C` | Same UTC playhead as map/scene |
| P4-5 | Add cross-view handoff between map, scene, and video | frontend state + selection contracts | `L4` + `L5` | `[ ]` | P4-1, P4-4 | `P4-C` | Select event once, inspect everywhere |
| P4-6 | Add object/detection overlay contract for future bounded CV sources | models + renderer hooks | `L0` + `L5` | `[ ]` | P4-2 | `P4-D` | Keep it schema-driven; real ML integration can follow later |
| P4-7 | Create pilot scenario fixtures for sensor-mode demos | fixtures + QA scripts | `L6` | `[ ]` | P4-1, P4-4 | `P4-D` | Needed for repeatable validation |

## Parallel execution notes

- `P4-1` and `P4-2` can begin at the same time.
- `P4-3` and `P4-4` can move in parallel once the source model is frozen.
- `P4-7` should be built early so UI and renderer work against stable fixtures.

## Validation

- switching render modes does not desync the timeline
- video and scene views stay locked to the same selected event/playhead
- camera sources expose provenance and time range clearly

## Gate review

- [ ] Render modes work
- [ ] Camera/video playback works
- [ ] Cross-view event inspection works
- [ ] Fixture-backed sensor demos are repeatable
