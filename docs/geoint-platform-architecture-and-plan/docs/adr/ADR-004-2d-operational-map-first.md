# ADR-004 — 2D operational map first; 3D globe second

## Status
Accepted

## Context
The frontend requires a primary map surface for analyst workflows (AOI selection, layer inspection, change review) and a secondary surface for stakeholder overview/storytelling. Two candidates emerged: MapLibre GL JS for 2D and globe.gl for 3D.

Analysts need precision — pixel-accurate geometry clicking, STAC footprint overlays, and track playback requiring stable coordinate reference — not spectacle. A globe view adds visual impact but creates ambiguity in click targets and complicates deck.gl layer integration.

## Decision
1. **MapLibre GL JS** is the primary operational map surface for all analyst-facing workflows.
2. **globe.gl** is integrated as a secondary view mode for overview and storytelling purposes only.
3. The 2D/3D toggle is deferred until Phase 2+ and scoped to read-only overview usage.

## Consequences
- All P1–P4 analyst workflows (AOI selection, imagery search, track playback, change review) are built and tested against MapLibre GL JS.
- deck.gl TripsLayer, GeoJSON sources, and heatmap layers are wired to MapLibre via the `DeckProps` overlay pattern.
- globe.gl integration remains a deferred deliverable (P2-5), without blocking any core release.
- If globe.gl is never needed, no sunk cost has been incurred in analyst-critical infrastructure.

## Implementation notes
- `frontend/src/components/Map/MapView.tsx` — MapLibre GL JS 5.x with deck.gl overlay
- `docs/geoint-platform-architecture-and-plan/docs/adr/ADR-005-deck-gl-dense-overlay-playback.md` — companion decision for overlay renderer
- P2-5 (globe.gl) remains `[-]` deferred per `HANDOVER.md`
