# Scene Performance Budgets

## Pilot AOIs

| AOI | Centre Coordinates | Notes |
|-----|-------------------|-------|
| Strait of Hormuz | 56.52°E, 26.35°N | Highest track density; primary demo target |
| Black Sea | 33.0°E, 43.0°N | Ship/aircraft + jamming events |
| Baltic Sea | 20.0°E, 57.0°N | Airspace restrictions scenario |

## Performance Budgets

### Globe / 3D Scene

| Metric | Budget | Measured How |
|--------|--------|--------------|
| Initial load time (globe → interactive) | < 3s desktop, < 5s mobile | Chrome Performance: `navigation.start` → `map.on('idle')` |
| Sustained FPS — idle scene | 60 FPS target, 30 FPS minimum | `requestAnimationFrame` delta averaged over 500ms windows |
| Sustained FPS — dense (200+ entities) | ≥ 30 FPS | Hormuz scenario with all trips visible |
| Time to interactive after AOI change | < 500ms | `performance.mark` + `performance.measure` |
| WebGL memory — baseline globe | < 200MB | Chrome DevTools Memory → GPU column |
| Layer add latency (new GeoJSON source) | < 200ms | `performance.now()` + `map.on('sourcedata')` |

### 2D Map

| Metric | Budget | Measured How |
|--------|--------|--------------|
| Initial tile load | < 2s desktop, < 4s mobile | `map.on('idle')` after `map.setCenter` |
| Sustained FPS — idle | 60 FPS target, 30 FPS minimum | Same RAF method |
| HeatmapLayer render latency | < 100ms | Time between data update and next frame |

## Dense View Throttling Strategy

When entity count > 500 (exposed by `useScenePerformance.isDenseView`):
- Reduce TripsLayer `trailLength` to 10% of normal
- Replace HeatmapLayer with ScatterplotLayer at radius/4
- Reduce PathLayer point sampling to 50%
- Disable orbit footprint rendering
- Show "density mode" indicator in scene corner

## Regression Triggers

A regression is declared when:
1. Idle FPS drops below 30 for more than 2 consecutive 500ms windows
2. Initial load time exceeds 4.5s on desktop
3. AOI-change latency exceeds 1000ms
4. WebGL memory grows > 50MB per navigation without GC

*Last updated: 2026-04-04 — Phase 3 Track D*
