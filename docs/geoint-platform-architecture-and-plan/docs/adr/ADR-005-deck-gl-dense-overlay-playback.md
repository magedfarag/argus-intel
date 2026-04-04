# ADR-005 — deck.gl owns dense overlay and playback rendering

## Status
Accepted

## Context
Rendering thousands of moving-object positions (AIS ships, ADS-B aircraft, GDELT event markers) as native MapLibre GL JS features causes frame-rate degradation. The animated track-trail use case specifically requires timestamped polyline rendering that MapLibre cannot express natively.

Three options were considered:
1. Native MapLibre GeoJSON layers — fast for static data, degrades under dynamic/dense load, no built-in playback primitives.
2. deck.gl over a WebGL2 canvas overlay — GPU-accelerated, supports `TripsLayer`, `ScatterplotLayer`, `HeatmapLayer`; integrates with MapLibre via `DeckProps`.
3. Three.js custom renderer — maximum flexibility, requires significant engineering investment.

## Decision
Use **deck.gl** (v9.x, `@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/geo-layers`) as the overlay renderer for:
- Maritime and aviation track trails (`TripsLayer`)
- Dense event point clouds (`ScatterplotLayer`)
- Future heatmap overlays

MapLibre GL JS remains the host map and handles basemap, AOI polygon drawing, imagery footprints, and GeoJSON layers with low feature counts.

## Consequences
- `frontend/package.json` includes `@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/geo-layers`, `@deck.gl/mapbox`.
- `MapView.tsx` instantiates a `DeckGL` component mounted over the `MapLibre` canvas.
- Track data is fed through `useTracks.ts` hook in timestamped `[lon, lat, timestamp]` format.
- Zoom-based degradation (hide below z=7) prevents rendering overload on low-resolution views.
- Any future 3D globe view (ADR-004, P2-5) must evaluate deck.gl compatibility with globe.gl separately.

## Implementation notes
- `frontend/src/components/Map/MapView.tsx` — `DeckGL` overlay + `TripsLayer` (ships: blue, aircraft: orange)
- `frontend/src/hooks/useTracks.ts` — polling hook converts TelemetryStore events to DeckGL trip format
- Performance budget: < 256 tiles at z=14, < 500 events before server-side density reduction fires
