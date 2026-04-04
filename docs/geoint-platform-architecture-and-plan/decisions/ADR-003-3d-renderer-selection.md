# ADR-003: 3D Renderer Selection

## Status
Accepted — 2026-04-04

## Context

The ARGUS frontend uses MapLibre GL JS (globe projection) + deck.gl via MapboxOverlay for all map surfaces. Phase 3 requires adding terrain elevation and 3D building primitives to the existing globe view.

Installed renderer stack:
- `maplibre-gl ^5.22.0` — 2D and globe rendering
- `@deck.gl/core ^9.2.11` — overlay rendering
- `@deck.gl/geo-layers ^9.2.11` — includes `Tile3DLayer`
- `@deck.gl/mapbox ^9.2.11` — MapboxOverlay integration

## Decision

**Extend the current stack: MapLibre GL JS terrain + deck.gl `Tile3DLayer`.**

No migration to CesiumJS or any other renderer.

## Options Considered

### Option 1 — MapLibre terrain + deck.gl Tile3DLayer (SELECTED)
- Terrain via MapLibre `terrain` spec + `raster-dem` source (SRTM via MapTiler or AWS)
- 3D buildings via `Tile3DLayer` from `@deck.gl/geo-layers` (OGC 3D Tiles)
- Migration cost: zero — all existing layers preserved
- Bundle impact: zero — `Tile3DLayer` already in bundle
- Risk: low — no new dependencies

### Option 2 — CesiumJS (rejected)
- Full rewrite of GlobeView required — 4–6 weeks estimated
- All deck.gl layers must be reimplemented as Cesium primitives
- Bundle +2–3 MB
- Rejected: migration cost disproportionate for demo/operational prototype

### Option 3 — Resium (rejected)
- Same as Option 2 with React wrappers — same cost/risk profile
- Rejected for same reasons as Option 2

## Consequences

- `GlobeView.tsx` gains terrain config pointing at a `raster-dem` source
- A `Tile3DLayer` is added to the deck.gl overlay for 3D buildings
- No existing layer logic changes
- Phase 3 Track C overlay porting is now limited to regression-testing at non-zero elevation

## Implementation Mandate

1. `maplibre-gl` + `@deck.gl/*` is the renderer pair — no CesiumJS within Phase 3 scope
2. DEM terrain source URL must be configurable, not hardcoded
3. 3D Tiles endpoint URL must also be env-variable configurable
4. `Tile3DLayer` must be an opt-in layer with its own visibility toggle
5. Do not upgrade `@deck.gl/*` versions as part of Phase 3
6. Do not alter existing camera controller settings

## Phase 3 Scope Impact

Track B is narrowed to two additions in `GlobeView.tsx`:
1. Add the `terrain` property with a `raster-dem` source
2. Add `Tile3DLayer` to the deck.gl overlay

Track C overlay porting is a no-op — all layers already exist in GlobeView. Regression testing only.
