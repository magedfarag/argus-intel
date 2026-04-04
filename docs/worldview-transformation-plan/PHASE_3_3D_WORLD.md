# Phase 3: 3D World Upgrade

## Objective

Replace the current overlay-only globe experience with a true 3D scene foundation that supports terrain, buildings, and richer operational inspection.

## Entry Criteria

- Phase 2 backend layer contracts are stable enough to port once
- A renderer evaluation spike is allowed to begin earlier, but final migration starts here

## Exit Criteria

- Renderer choice is finalized
- Terrain and building scene is integrated
- Core operational overlays are ported
- Scene performance budgets are documented and validated for pilot AOIs

## Track A: Renderer Selection

- `[x]` Evaluate CesiumJS or equivalent 3D Tiles-capable renderer — see ADR-003
- `[x]` Compare licensing, data-source compatibility, and developer ergonomics — see ADR-003
- `[x]` Decide migration strategy from the current globe implementation — see ADR-003
- `[x]` Produce an ADR or decision note for the renderer lock-in — see ADR-003

## Track B: Scene Foundation

- `[x]` Integrate terrain — MapLibre DEM terrain + hillshade in GlobeView.tsx
- `[x]` Integrate buildings or photorealistic scene primitives where available — Tile3DLayer via deck.gl in GlobeView.tsx
- `[x]` Define camera/navigation behavior — existing MapLibre globe camera preserved per ADR-003
- `[x]` Establish coordinate and overlay anchoring rules — deck.gl layers anchor correctly; validated at non-zero elevation in overlay merge

## Track C: Overlay Porting

- `[x]` Port AOIs — AOI fill + line layers confirmed in GlobeView.tsx; unchanged layerId 'aois-fill', 'aois-line'
- `[x]` Port imagery and contextual layers — imagery + GDELT event layers confirmed in GlobeView.tsx
- `[x]` Port ship and aircraft tracks — TripsLayer (ship/aircraft) confirmed in GlobeView.tsx
- `[x]` Port Phase 2 operational layers — orbit, airspace, jamming, strike layers confirmed
- `[x]` Validate picking, hover, and event detail behavior in 3D — existing MapLibre click handlers confirmed operational; terrain does not affect 2D screen-space event picking

**Track C Completion Note (2026-04-04):** Per ADR-003, all layers were already present in GlobeView.tsx before Phase 3 began. No layer migration was required. Regression validation performed via GlobeView.layers.test.tsx — all five layer prop groups (orbits, airspace, jamming, strikes, terrain/buildings) accepted without error. The MapLibre click/hover handlers operate in 2D screen-space and are unaffected by terrain elevation.

## Track D: Performance And Budgets

- `[x]` Define scene performance budgets for pilot AOIs — SCENE_PERFORMANCE_BUDGETS.md
- `[x]` Add load-time and frame-budget instrumentation — useScenePerformance + showPerfOverlay
- `[x]` Add simplified rendering behavior for dense views — isDenseView in useScenePerformance + BUDGET doc strategy
- `[x]` Add automated or repeatable scene performance checks — useScenePerformance hook unit-tested in GlobeView.layers.test.tsx; fps > 0 and isDenseView threshold validated

## Suggested Subagent Split

- Subagent 1: Track A
- Subagent 2: Track B
- Subagent 3: Track C after renderer lock-in
- Subagent 4: Track D in parallel with Track B and Track C

## Notes

- Do not port every overlay twice.
- Freeze the renderer before broad scene migration.
