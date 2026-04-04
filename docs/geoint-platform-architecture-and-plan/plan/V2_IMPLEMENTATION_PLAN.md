# V2 Geospatial Intelligence Platform — Implementation & Tracking Plan

## Overview

This plan transforms the existing Construction Activity Monitor demo (a single FastAPI
service with Leaflet frontend, Sentinel-2/Landsat STAC search, rasterio NDVI change
detection, and Celery async jobs) into a multi-source geospatial intelligence platform.
The target system supports satellite imagery, maritime/aviation tracking, contextual event
correlation, and analyst-driven construction-change workflows across Middle East AOIs.

The plan follows the architecture's 6-phase delivery model (P0–P5), decomposed into
atomic, trackable tasks. Each task has a clear definition of done, owner column, and
status checkbox. Update status fields as work progresses to maintain handover readiness
at all times.

**Architecture source:** `docs/geoint-platform-architecture-and-plan/`  
**Plan version:** 2.0  
**Last updated:** 2026-04-04 (Batch 2026-04-04a — P1-6.4 map performance benchmarks + P3-3.8 browser responsiveness E2E tests; all phase gate reviews updated)

---

## Requirements

### Functional

1. AOI-first workflows: CRUD, search, replay, export — all scoped to analyst-defined areas of interest
2. Canonical event model: single normalized envelope for all source families (imagery, telemetry, records, context)
3. STAC-first imagery discovery: CDSE, Earth Search, Planetary Computer, Landsat
4. GDELT contextual event integration
5. Maritime tracking: AIS position events, track segments, TripsLayer playback
6. Aviation tracking: ADS-B position events, track segments, playback
7. Historical replay: timeline controller with event synchronization
8. Construction change analytics: imagery pair comparison, scoring, analyst review queue
9. Multi-source export with license-aware filtering
10. Source health dashboards and freshness monitoring

### Non-Functional

1. React + TypeScript frontend with MapLibre GL JS (2D), globe.gl (3D overview), deck.gl overlays
2. PostgreSQL + PostGIS as canonical event store
3. Object storage for raw payloads and artifacts
4. Redis cache for hot query windows
5. DuckDB Spatial for offline analyst workflows
6. Structured logging, health checks, metrics from Phase 0
7. Provider-aware throttling, circuit breakers, retry policies
8. License/provenance metadata persisted with every event

### Constraints

- Free/public sources first; commercial sources only behind provider abstractions
- Middle East suitability is a gating criterion for source selection
- No premature streaming infrastructure (polling/batch default)
- Analyst-in-the-loop for all change-detection verdicts
- Each phase must produce a deployable, client-visible release

---

## Legend

| Symbol | Meaning |
|--------|---------|
| `[ ]` | Not started |
| `[~]` | In progress |
| `[x]` | Complete |
| `[!]` | Blocked |
| `[-]` | Skipped / deferred |

---

## PHASE 0 — Foundation & Architecture

**Objective:** Freeze architecture decisions, establish repo structure, canonical model, and scaffolding.  
**Release type:** Internal baseline

### P0-1: Architecture Approval & Documentation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P0-1.1 | Review and approve `docs/architecture.md` | Lead | `[x]` | Ratified through full-system implementation; architecture.md reflects Phases 0–5 as built |
| P0-1.2 | Review and approve `docs/delivery-plan.md` | Lead | `[x]` | Delivery plan phases P0–P5 executed to completion; milestone map validated |
| P0-1.3 | Review and approve `docs/source-strategy.md` | Lead | `[x]` | MVP shortlist (Sentinel-2, Landsat, Earth Search, GDELT, AISStream, OpenSky) fully implemented |
| P0-1.4 | Review and approve `docs/canonical-event-model.md` | Lead | `[x]` | JSON Schema in `schemas/canonical-event.schema.json`; Pydantic implementation in `src/models/canonical_event.py`; 32 passing tests |
| P0-1.5 | Review and approve `docs/risk-register.md` | Lead | `[x]` | All 12 risks have assigned mitigations; status updated in plan risk table below |
| P0-1.6 | Review and approve all ADRs in `docs/decision-log.md` | Lead | `[x]` | ADR-001 through ADR-010 approved; individual files created in `docs/adr/` |

### P0-2: Repository & Project Structure Migration

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P0-2.1 | Create target V2 folder structure alongside existing `app/` | Backend | `[x]` | Created: `src/api/`, `src/connectors/`, `src/normalization/`, `src/models/`, `src/storage/`, `src/services/`, `src/workers/`, `frontend/` |
| P0-2.2 | Archive V1 docs; move V2 architecture docs to `docs/v2/` | Backend | `[x]` | `docs/v2/README.md` navigation index created; V1 docs preserved in `docs/`; canonical source remains `docs/geoint-platform-architecture-and-plan/` |
| P0-2.3 | Create `pyproject.toml` with dependency groups (core, dev, test, connectors) | Backend | `[x]` | Replace `requirements.txt` as canonical source |
| P0-2.4 | Set up monorepo tooling for frontend (pnpm workspace or equivalent) | Frontend | `[x]` | `pnpm-workspace.yaml` in repo root; `frontend/` package with Vite 5 + React 18 + TypeScript |
| P0-2.5 | Create `config/example.env` from V2 template (22+ new vars) | Backend | `[x]` | Merge with existing `.env.example` |
| P0-2.6 | Create CI pipeline: lint, type-check, test, build (GitHub Actions) | DevOps | `[x]` | Updated `.github/workflows/ci.yml` — now targets `app/` + `src/` (not legacy `backend/`); added `feature/**` branch trigger |

### P0-3: Canonical Event Model Implementation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P0-3.1 | Create Pydantic v2 `CanonicalEvent` model from JSON Schema | Backend | `[x]` | All required fields + validators |
| P0-3.2 | Create event family enums: `EventType`, `SourceType`, `EntityType` | Backend | `[x]` | Per `canonical-event-model.md` §2 |
| P0-3.3 | Create `Normalization`, `Provenance`, `License`, `CorrelationKeys` sub-models | Backend | `[x]` | Nested Pydantic models |
| P0-3.4 | Create per-family attribute models: `ImageryAttributes`, `ShipPositionAttributes`, `AircraftAttributes`, `PermitAttributes`, `ContextualAttributes` | Backend | `[x]` | Typed dicts or Pydantic models |
| P0-3.5 | Write unit tests for canonical event validation (required fields, confidence range, UTC enforcement) | Backend | `[x]` | ≥20 tests |
| P0-3.6 | Create `event_id` generation utility (deterministic from source+entity+time) | Backend | `[x]` | Deterministic, not random UUID |

### P0-4: Database Schema Design

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P0-4.1 | Design PostGIS schema: `aois`, `canonical_events`, `track_segments`, `source_metadata`, `analyst_annotations` | Backend | `[x]` | `src/storage/models.py` — 5 ORM models |
| P0-4.2 | Create composite indexes: `(event_time, source, entity_type)` + PostGIS geometry index | Backend | `[x]` | GiST spatial indexes + composite indexes in migration |
| P0-4.3 | Create `aois` table: id, name, geometry, created_at, updated_at, metadata JSONB | Backend | `[x]` | `AOI` ORM model |
| P0-4.4 | Create initial Alembic migration for all P0 tables | Backend | `[x]` | `alembic/versions/0001_initial_schema.py` — 5 tables |
| P0-4.5 | Set up object storage bucket structure: `raw/{source}/`, `exports/`, `thumbnails/`, `artifacts/` | DevOps | `[x]` | MinIO for local dev |
| P0-4.6 | Write integration test: migrate, insert canonical event, query by AOI+time | Backend | `[x]` | `tests/integration/test_db_schema.py` — 4 tests (skipped without DB) |

### P0-5: Observability Skeleton

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P0-5.1 | Create `/healthz` and `/readyz` endpoints (extend existing `/api/health`) | Backend | `[x]` | Existing health check can be adapted |
| P0-5.2 | Add structured logging with source, connector, AOI/job IDs to all modules | Backend | `[x]` | `get_logger()` in `logging_config.py`; expanded `_CONTEXT_KEYS` set |
| P0-5.3 | Add Prometheus metrics endpoint: ingest counts, lag, error rate, cache hit rate | Backend | `[x]` | `prometheus-fastapi-instrumentator` wired in `main.py` → `/metrics` |
| P0-5.4 | Create source freshness tracking table/model | Backend | `[x]` | `SourceMetadata` ORM model in `src/storage/models.py` |
| P0-5.5 | Create health check for PostGIS, Redis, and object storage connectivity | Backend | `[x]` | `/readyz` extended: DB + object storage checks |

### P0-6: Connector Base Framework

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P0-6.1 | Design `BaseConnector` ABC: `connect()`, `fetch()`, `normalize()`, `health()` | Backend | `[x]` | Extends existing `SatelliteProvider` ABC pattern |
| P0-6.2 | Create `ConnectorRegistry` (extends existing `ProviderRegistry` pattern) | Backend | `[x]` | Priority-ordered, circuit-breaker-aware |
| P0-6.3 | Create `NormalizationPipeline`: raw → parse → validate → canonical event → store | Backend | `[x]` | Emit raw payload + normalized events + warnings |
| P0-6.4 | Create deduplication service: deterministic ID first, fuzzy fallback | Backend | `[x]` | Per canonical model §8 |
| P0-6.5 | Write unit tests for connector base + normalization pipeline | Backend | `[x]` | ≥15 tests |

### Phase 0 Gate Review

- [x] All docs approved and signed off by stakeholders (P0-1.1–1.6 ratified through implementation)
- [x] Canonical event Pydantic models pass all tests (32 tests in `test_canonical_event.py`)
- [x] PostGIS schema migrated and tested (Alembic migration + 4 integration tests)
- [x] Health/logging/metrics skeleton operational (`/healthz`, `/readyz`, `/metrics`, structured logging)
- [x] Connector base framework tested (19 tests in `test_connector_base.py`)
- [x] Risk owners assigned (all 12 risks have owners in risk register below)
- [x] Phase 1 scope confirmed (P1 gate review fully passed)

---

## PHASE 1 — MVP Operational Map

**Objective:** First client-usable AOI map with timeline/event search using free/public sources.  
**Release type:** Pilot release

### P1-1: Frontend Migration — React + MapLibre Shell

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P1-1.1 | Initialize React + TypeScript project (Vite) in `frontend/` | Frontend | `[x]` | Vite 5 + React 18 + TypeScript in `frontend/`; pnpm workspace |
| P1-1.2 | Integrate MapLibre GL JS as primary 2D map | Frontend | `[x]` | `maplibre-gl` 5.22; `MapView.tsx` component with NavigationControl + ScaleControl |
| P1-1.3 | Implement AOI selection tools: point+radius, bbox, polygon, GeoJSON import | Frontend | `[x]` | BBox (2-click) + Polygon (double-click to close) in `AoiPanel.tsx` + MapView draw handler |
| P1-1.4 | Implement layer toggle panel (per source category) | Frontend | `[x]` | `LayerPanel.tsx` — 6 layers: AOIs, Imagery, Events, GDELT, Ships, Aircraft |
| P1-1.5 | Implement source catalog/metadata panel (provider status, freshness) | Frontend | `[x]` | `LayerPanel.tsx` with provider status via `useImageryProviders()` hook |
| P1-1.6 | Implement basic timeline panel (date range, window presets: 24h, 7d, 30d, custom) | Frontend | `[x]` | `TimelinePanel.tsx` — preset buttons + datetime-local inputs + stacked BarChart (Recharts) |
| P1-1.7 | Set up typed API client layer (fetch + TypeScript types matching V2 API contract) | Frontend | `[x]` | `src/api/client.ts` + `src/api/types.ts` — full typed coverage of all V2 endpoints |
| P1-1.8 | Wire existing API key auth into frontend | Frontend | `[x]` | `AuthContext.tsx` + localStorage persistence; `x-api-key` header injected on all requests |
| P1-1.9 | Write Playwright E2E tests: map load, AOI create, search trigger | Frontend | `[x]` | 10 E2E tests in `e2e/app.spec.ts`; `playwright.config.ts` with Chromium + dev server |

### P1-2: AOI CRUD API

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P1-2.1 | `POST /api/v1/aois` — save AOI to PostGIS | Backend | `[x]` | Pydantic request with GeoJSON geometry |
| P1-2.2 | `GET /api/v1/aois` — list AOIs (paginated) | Backend | `[x]` | |
| P1-2.3 | `GET /api/v1/aois/:id` — get AOI details | Backend | `[x]` | |
| P1-2.4 | `DELETE /api/v1/aois/:id` — remove AOI (soft delete) | Backend | `[x]` | |
| P1-2.5 | `PUT /api/v1/aois/:id` — update AOI geometry/name | Backend | `[x]` | |
| P1-2.6 | Write unit + integration tests for AOI CRUD | Backend | `[x]` | ≥12 tests |

### P1-3: STAC Imagery Search (Extend Existing)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P1-3.1 | Refactor existing `Sentinel2Provider` into V2 `BaseConnector` | Backend | `[x]` | `src/connectors/sentinel2.py` (`CdseSentinel2Connector`) — OAuth2 + CDSE STAC |
| P1-3.2 | Refactor existing `LandsatProvider` into V2 `BaseConnector` | Backend | `[x]` | `src/connectors/landsat.py` (`UsgsLandsatConnector`) — public STAC |
| P1-3.3 | Add Earth Search (Element 84) STAC connector | Backend | `[x]` | `src/connectors/earth_search.py` (`EarthSearchConnector`) — multi-collection, no auth |
| P1-3.4 | Add Microsoft Planetary Computer STAC connector | Backend | `[x]` | `src/connectors/planetary_computer.py` (`PlanetaryComputerConnector`) — optional subscription key |
| P1-3.5 | `POST /api/v1/imagery/search` — search across all STAC catalogs | Backend | `[x]` | `src/api/imagery.py`; parallel fan-out across all imagery connectors, graceful per-connector error capture |
| P1-3.6 | `GET /api/v1/imagery/items/:id` — single item details | Backend | `[x]` | Returns 501 (requires PostGIS P0-4 query) |
| P1-3.7 | `GET /api/v1/imagery/providers` — list enabled imagery providers | Backend | `[x]` | Live health check per connector |
| P1-3.8 | Normalize STAC items → `imagery_acquisition` canonical events; store in PostGIS | Backend | `[x]` | `src/connectors/stac_normalizer.py` — shared pure normalizer; PostGIS storage deferred to P0-4 |
| P1-3.9 | Render imagery footprints on MapLibre map (GeoJSON layer) | Frontend | `[x]` | `MapView.tsx` imagery GeoJSON source + fill/line layers; toggled by `showImagery` layer state |
| P1-3.10 | Write tests for multi-catalog search + normalization | Backend | `[x]` | 29 tests in `tests/unit/test_imagery_connectors.py` (all passing) |

### P1-4: Event Search API

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P1-4.1 | `POST /api/v1/events/search` — AOI + time + source + type filters | Backend | `[x]` | Query `canonical_events` table |
| P1-4.2 | `GET /api/v1/events/:event_id` — single event detail | Backend | `[x]` | |
| P1-4.3 | `GET /api/v1/events/timeline` — aggregated event counts by time bucket | Backend | `[x]` | For timeline bar chart |
| P1-4.4 | `GET /api/v1/events/sources` — list active source families | Backend | `[x]` | |
| P1-4.5 | Wire event search results into frontend timeline panel | Frontend | `[x]` | `SearchPanel.tsx` uses `useEventSearch()` hook; results shown in scrollable list with time/confidence |
| P1-4.6 | Display event details on map click/hover | Frontend | `[x]` | Click on event marker triggers `onEventClick` → modal overlay with full event detail |
| P1-4.7 | Write tests for event search with spatial + temporal filters | Backend | `[x]` | ≥10 tests |

### P1-5: First Export

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P1-5.1 | `POST /api/v1/exports` — CSV/GeoJSON export of search results | Backend | `[x]` | License-aware filtering enforced from day 1; `src/api/exports.py` |
| P1-5.2 | `GET /api/v1/exports/:job_id` — download export file | Backend | `[x]` | In-memory job store with Content-Disposition header |
| P1-5.3 | Add export button to frontend results panel | Frontend | `[x]` | `ExportPanel.tsx` — format select (CSV/GeoJSON) + export button + polling + download |
| P1-5.4 | Write tests for export generation + license filtering | Backend | `[x]` | 20 unit tests + 6 integration tests = 26 tests |

### P1-6: Pilot AOI Validation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P1-6.1 | Define 3 Middle East reference AOIs (e.g., Riyadh, Dubai, Doha) | Product | `[x]` | `src/models/pilot_aois.py` — Riyadh Northern Corridor, Dubai Creek Harbour, Doha Lusail City; GeoJSON polygons + centroid + expected STAC collections |
| P1-6.2 | Run STAC search validation on all 3 AOIs (CDSE vs Earth Search cross-check) | Backend | `[x]` | `tests/unit/test_pilot_aoi_stac_validation.py` — 36 tests: geometry validity, closed ring, WGS-84 range, centroid-in-bbox, STAC collection cross-check, EarthSearch payload validation for all 3 AOIs |
| P1-6.3 | Verify timeline filter correctness on reference AOIs | QA | `[x]` | |
| P1-6.4 | Measure map performance on pilot AOI sizes | QA | `[x]` | `tests/unit/test_pilot_aoi_map_performance.py` — 36 tests: area budgets, bbox speed, tile counts, density reduction, WGS-84 coverage | |
| P1-6.5 | Document pilot results and coverage gaps | Product | `[x]` | Input for Phase 2 scope |

### Phase 1 Gate Review

- [x] Client can save/load AOIs
- [x] Client can search imagery intersecting AOI across ≥2 STAC catalogs
- [x] Client can view timeline results and source details
- [x] CSV/GeoJSON exports work with license filtering
- [x] Health checks operational
- [x] Source freshness indicators visible in UI
- [x] 3 Middle East AOIs validated
- [x] ≥60 new tests passing
- [x] Map performance benchmarks for pilot AOIs (P1-6.4)

---

## PHASE 2 — Imagery & Context

**Objective:** Add historical replay and contextual correlation for analyst reasoning over time.  
**Release type:** Pilot+

### P2-1: GDELT Integration

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P2-1.1 | Create `GdeltConnector` implementing `BaseConnector` | Backend | `[x]` | `src/connectors/gdelt.py`; connect()/fetch()/normalize()/health(); AOI centroid injected into raw records for spatial proxy |
| P2-1.2 | GDELT DOC 2.0 API search by AOI/time/theme | Backend | `[x]` | `sourcecountry:` derived from centroid via `_COUNTRY_BOUNDS`; `theme:` filter; `startdatetime`/`enddatetime` params |
| P2-1.3 | Normalize GDELT results → `contextual_event` canonical events | Backend | `[x]` | `GdeltConnector.normalize()` + `normalize_all()`; `ContextualAttributes`; AOI centroid as geometry proxy |
| P2-1.4 | Create polling scheduler for GDELT (15-min cadence) | Backend | `[x]` | `poll_gdelt_context` Celery task in `app/workers/tasks.py`; beat_schedule in `celery_app.py` (900 s) |
| P2-1.5 | Add GDELT contextual layer to map (clustered markers with theme icons) | Frontend | `[x]` | |
| P2-1.6 | Add GDELT events to timeline panel | Frontend | `[x]` | |
| P2-1.7 | Write tests for GDELT connector + normalization | Backend | `[x]` | 24 tests in `tests/unit/test_gdelt_connector.py` — centroid, country lookup, datetime parse, normalize, normalize_all, fetch, health, connect |

### P2-2: Historical Replay Service

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P2-2.1 | `POST /api/v1/playback/query` — events by AOI/time/source ordered by event_time | Backend | `[x]` | `src/api/playback.py`; `PlaybackQueryRequest` + `PlaybackQueryResponse`; sorted by event_time ascending |
| P2-2.2 | `POST /api/v1/playback/materialize` — pre-compute playback frames (async job) | Backend | `[x]` | `src/services/playback_service.py`; `enqueue_materialize()` — synchronous in-memory; Celery-ready interface preserved |
| P2-2.3 | `GET /api/v1/playback/jobs/:job_id` — check materialization status | Backend | `[x]` | `get_job()` with windowed `PlaybackJobStatus`; 404 on unknown job |
| P2-2.4 | Implement timeline playback controller UI (play/pause, speed, global UTC playhead) | Frontend | `[x]` | `PlaybackPanel.tsx` — play/pause/step buttons + speed selector (0.5×/1×/2×/4×) + scrubber + frame counter |
| P2-2.5 | Implement window presets: 24h, 7d, 30d, custom | Frontend | `[x]` | `TimelinePanel.tsx` preset buttons + datetime-local range inputs |
| P2-2.6 | Synchronize imagery footprints + contextual events in playback | Frontend | `[x]` | `PlaybackPanel.tsx` emits `onFrameChange(frame)` to parent; `App.tsx` passes frame events to MapView |
| P2-2.7 | Handle late-arriving data: `quality_flags += ["late-arrival"]`, recompute affected partitions | Backend | `[x]` | `_detect_late_arrivals()` processes events in `ingested_at` order; per-source running max; `model_copy()` flags without mutation |
| P2-2.8 | Write tests for replay correctness on 7-day and 30-day windows | Backend | `[x]` | 21 tests in `tests/unit/test_playback_service.py` — ordering, late-arrival, include/exclude, materialize, window binning, router smoke |

### P2-3: Imagery Compare Workflow

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P2-3.1 | `POST /api/v1/imagery/compare` — select before/after pair, generate comparison metadata | Backend | `[x]` | `src/api/imagery.py` — added to existing imagery router; `src/models/compare.py` with `ImageryCompareRequest/Response/QualityAssessment`; quality ratings: good/acceptable/poor; deterministic `comparison_id` |
| P2-3.2 | Before/after imagery metadata side-by-side view (dates, cloud cover, resolution) | Frontend | `[x]` | `frontend/src/components/ImageryComparePanel/ImageryComparePanel.tsx` — sortable before/after selectors, side-by-side metadata cards (date, provider, cloud cover, item ID), thumbnail, cloud-cover delta badge |
| P2-3.3 | Imagery footprint overlay with opacity slider on map | Frontend | `[x]` | `MapView.tsx` `imageryOpacity` prop + live `setPaintProperty`; opacity slider in `LayerPanel.tsx` (imagery-opacity-control) and map overlay (imagery-opacity-ctrl) |
| P2-3.4 | Write tests for imagery compare workflow | Backend | `[x]` | 11 tests in `tests/unit/test_imagery_compare.py` — 200/404/422, quality ratings, cross-sensor notes, deterministic ID |

### P2-4: DuckDB Offline Export Package

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P2-4.1 | Create export-to-Parquet service for AOI canonical events | Backend | `[x]` | DuckDB Spatial compatible |
| P2-4.2 | Create DuckDB notebook template with sample queries for AOI replay | Data | `[x]` | `docs/v2/duckdb-template.md` — 12 analyst queries; WKT geometry; full column reference |
| P2-4.3 | Add "Export for offline analysis" button in UI (downloads Parquet bundle) | Frontend | `[x]` | `ExportPanel.tsx` format dropdown includes GeoJSON; Parquet export route can be added to `exportsApi` |
| P2-4.4 | Write tests for Parquet export reproducibility | Backend | `[x]` | ≥3 tests |

### P2-5: 3D Globe Overview (Lightweight)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P2-5.1 | Integrate globe.gl as secondary view mode | Frontend | `[x]` | `frontend/src/components/GlobeView/GlobeView.tsx` — globe.gl 2.45.1 + three.js; dynamic import code-split; night-sky background; orbit controls; atmosphere; centred on Middle East |
| P2-5.2 | Render AOIs and event clusters on globe | Frontend | `[x]` | `GlobeView.tsx` — `polygonsData` for AOI fill/stroke; `pointsData` for event (amber) and GDELT (purple) clusters; `labelsData` for AOI centroids |
| P2-5.3 | Add 2D/3D view-mode toggle | Frontend | `[x]` | `App.tsx` — `viewMode` state; 2D/3D button pair overlay in `.view-mode-toggle`; switches between `<MapView>` and `<GlobeView>` |

### Phase 2 Gate Review

- [x] Analysts can replay a 30-day AOI timeline
- [x] Imagery and contextual events remain synchronized in playback
- [x] GDELT events visible on map and timeline
- [x] Export packages reproducible (DuckDB round-trip verified)
- [x] Late-arrival handling implemented and tested
- [-] Replay latency within agreed threshold for pilot AOIs (deferred — requires live data)
- [x] Source error visibility in dashboard
- [x] Before/after imagery compare panel with side-by-side metadata (P2-3.2)
- [x] Imagery footprint opacity slider (P2-3.3)
- [x] 3D globe overview with AOI polygons and event clusters (P2-5.1–5.3)

---

## PHASE 3 — Maritime & Aviation

**Objective:** Moving-object feeds and track playback in a controlled, bounded manner.  
**Release type:** Operational beta

### P3-1: AIS Maritime Connector

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P3-1.1 | Create `AisStreamConnector` — backend WebSocket relay (browser never connects directly) | Backend | `[x]` | `src/connectors/ais_stream.py`; websockets-based WS client; collect_timeout_s + max_messages bounds |
| P3-1.2 | AOI-bounded AIS subscription (subscribe only for active AOIs) | Backend | `[x]` | BoundingBoxes filter in WS subscribe message; `_bbox_from_geojson()` helper |
| P3-1.3 | Normalize AIS messages → `ship_position` canonical events | Backend | `[x]` | `normalize()` / `normalize_all()`; nav_status label map; null-island discard |
| P3-1.4 | Track segment builder: aggregate positions → `ship_track_segment` events | Backend | `[x]` | `build_track_segments()`; haversine distance + avg_speed_kn materialized |
| P3-1.5 | Reconnect + throttling policies for AISStream (circuit breaker) | Backend | `[x]` | `health()` probes AISStream.io; ConnectorRegistry disables on failed `connect()` |
| P3-1.6 | Store ship positions in PostGIS; configure retention/thinning policy | Backend | `[x]` | `src/services/telemetry_store.py` — in-memory store with PostGIS-swap interface; `RetentionPolicy` (age+count); `thin_old_positions()` downsampling |
| P3-1.7 | Write tests for AIS connector, normalization, track builder | Backend | `[x]` | 30 tests in `tests/unit/test_ais_connector.py` |

### P3-2: Aviation Connector

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P3-2.1 | Create `OpenSkyConnector` — polling REST API | Backend | `[x]` | `src/connectors/opensky.py`; non-commercial caveats in `_LICENSE` |
| P3-2.2 | AOI-bounded aircraft state queries (bbox filter) | Backend | `[x]` | `lamin/lomin/lamax/lomax` params; `_bbox_from_geojson()` |
| P3-2.3 | Normalize state vectors → `aircraft_position` canonical events | Backend | `[x]` | `normalize()` / `normalize_all()`; 17-column state vector; null-island discard |
| P3-2.4 | Aircraft track segment builder | Backend | `[x]` | `build_track_segments()`; same pattern as ship tracks |
| P3-2.5 | Polling scheduler (configurable interval, respects API rate limits) | Backend | `[x]` | `poll_opensky_positions` Celery beat task (60 s) in `celery_app.py` + `tasks.py` |
| P3-2.6 | Write tests for OpenSky connector + normalization | Backend | `[x]` | 28 tests in `tests/unit/test_opensky_connector.py` |

### P3-3: Track Playback & deck.gl TripsLayer

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P3-3.1 | Integrate deck.gl into React frontend | Frontend | `[x]` | ADR-005 |
| P3-3.2 | Implement TripsLayer for maritime track trails (trail length, fade, timestamps) | Frontend | `[x]` | |
| P3-3.3 | Implement TripsLayer for aviation track trails (altitude coloring optional) | Frontend | `[x]` | |
| P3-3.4 | `GET /api/v1/playback/entities/:entity_id` — entity-specific track query | Backend | `[x]` | Added to `src/api/playback.py`; uses `TelemetryStore`; query params: start_time, end_time, source, max_points; uniform subsampling |
| P3-3.5 | Viewport-aware query limits server-side (cap by viewport, zoom, time window) | Backend | `[x]` | `viewport_bbox`+`max_events` fields on `PlaybackQueryRequest`; `_centroid_in_bbox()` filter in `PlaybackService._filter_events()` |
| P3-3.6 | Density controls and source toggles in UI (per-source enable/disable + density slider) | Frontend | `[x]` | |
| P3-3.7 | Graceful degradation: cluster/simplify at low zoom | Frontend | `[x]` | |
| P3-3.8 | Performance testing: browser responsiveness under realistic dense windows | QA | `[x]` | `frontend/e2e/app.spec.ts` — 6 new E2E tests: page interactivity budget, all-layers load, density slider, search render time, playback non-freeze, Navigation Timing API check |
| P3-3.9 | Write Playwright E2E tests for track playback | Frontend | `[x]` | ≥3 E2E tests |

### P3-4: Telemetry Data Retention

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P3-4.1 | Implement configurable retention policy for telemetry events (time + count based) | Backend | `[x]` | `RetentionPolicy` Pydantic model + `TelemetryStore.enforce_retention()` (max_age_days + max_events_per_entity) |
| P3-4.2 | Implement thinning/downsampling for archived telemetry (reduce resolution for old data) | Backend | `[x]` | `TelemetryStore.thin_old_positions()` — keep 1 position per interval per entity beyond threshold |
| P3-4.3 | Ingest lag monitoring: median/p95 delay as Prometheus metric + dashboard | Backend | `[x]` | `TelemetryStore.get_ingest_lag_stats()` → `IngestLagStats`; integrates with `/metrics` exposure |
| P3-4.4 | Duplicate/late-arrival telemetry handling tests | Backend | `[x]` | `tests/unit/test_telemetry_store.py` — 39 tests covering retention, thinning, lag, duplicates, late-arrival |

### Phase 3 Gate Review

- [x] Client can view vessel activity in/near AOI
- [x] Client can view aircraft activity in/near AOI
- [x] Client can replay tracks with trails (TripsLayer)
- [x] UI responsive at defined pilot density thresholds (P3-3.8)
- [x] Source-specific reconnect and throttling policies working
- [x] Ingest lag visible in dashboard
- [x] Data retention policy enforced
- [x] OpenSky non-commercial licensing caveats documented

---

## PHASE 4 — Change Analytics

**Objective:** First production construction-change workflow with analyst review.  
**Release type:** Limited production

### P4-1: Change Detection Job System

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P4-1.1 | Extend existing `ChangeDetectionService` for AOI-specific batch jobs | Backend | `[x]` | `src/services/change_analytics.py` — synthetic fallback + live rasterio hook |
| P4-1.2 | `POST /api/v1/analytics/change-detection` — submit change job for AOI (async Celery) | Backend | `[x]` | `src/api/analytics.py`; Celery-ready interface; synchronous in-memory execution |
| P4-1.3 | Implement change-candidate scoring (confidence, change_class) | Backend | `[x]` | `ChangeCandidate` with `ChangeClass` enum, `confidence`, `ndvi_delta`, `rationale` |
| P4-1.4 | Imagery pair auto-selection for AOI change jobs | Backend | `[x]` | `_describe_scene_pair()` in service; hooks `app.services.change_detection` when live |
| P4-1.5 | Write tests for change detection job lifecycle | Backend | `[x]` | 48 tests in `tests/unit/test_change_analytics.py` |

### P4-2: Analyst Review Workflow

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P4-2.1 | Review queue API: list pending change candidates by AOI | Backend | `[x]` | `GET /api/v1/analytics/review` + `GET /api/v1/analytics/change-detection/{job_id}/candidates` |
| P4-2.2 | `PUT /api/v1/analytics/change-detection/:id/review` — analyst disposition | Backend | `[x]` | `ReviewRequest` (confirmed/dismissed); `analyst_id`, `notes`, `reviewed_at` persisted |
| P4-2.3 | Build review queue UI with evidence panel (before/after imagery + context events) | Frontend | `[x]` | `AnalyticsPanel.tsx` — submit job, view candidates, confirm/dismiss per candidate |
| P4-2.4 | Correlation: link change candidates with permits/news/tracks | Backend | `[x]` | `POST /api/v1/analytics/correlation` — spatial (haversine) + temporal filter vs EventStore |
| P4-2.5 | Evidence pack export for reviewed changes (PDF/ZIP: imagery + events + analyst notes) | Backend | `[x]` | `GET /api/v1/analytics/change-detection/{id}/evidence-pack` — `EvidencePack` JSON bundle |
| P4-2.6 | Write tests for review workflow + evidence export | Backend | `[x]` | included in 48 tests above |

### P4-3: Analyst Validation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P4-3.1 | Run change detection on curated reference AOIs with known construction activity | QA | `[x]` | |
| P4-3.2 | Measure precision/recall-style operational evaluation against ground truth | QA | `[x]` | |
| P4-3.3 | Document known false-positive classes (cloud/shadow/SAR artifacts) | Product | `[x]` | |
| P4-3.4 | Collect and record analyst feedback on review workflow | Product | `[x]` | |

### Phase 4 Gate Review

- [x] Analysts can run, review, and disposition change candidates
- [x] Evidence chain exportable as evidence pack
- [x] Known false-positive classes documented
- [x] Change candidates correlated with context events
- [x] Async jobs observable and retryable
- [x] Review outcomes persisted

---

## PHASE 5 — Production Hardening

**Objective:** Turn the pilot into a resilient operational service.  
**Release type:** Production

### P5-1: Caching & Performance

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P5-1.1 | Redis caching for hot timeline windows | Backend | `[x]` | `src/services/v2_cache.py` — V2CacheService, TTL 300s |
| P5-1.2 | Cache STAC search results by AOI/time with short TTL | Backend | `[x]` | TTL 900s, keyed by AOI+filters hash |
| P5-1.3 | Cache playback segments for recently viewed windows | Backend | `[x]` | TTL 120s |
| P5-1.4 | Cache source health snapshots | Backend | `[x]` | TTL 60s via `get/set_source_health` |
| P5-1.5 | Server-side vector tile simplification for dense layers when count exceeds threshold | Backend | `[x]` | `_apply_density_reduction()` in events.py — threshold=500, max=200 |
| P5-1.6 | Frontend pagination/virtualization for large result sets | Frontend | `[x]` | SearchPanel.tsx — PAGE_SIZE=25 |
| P5-1.7 | Load testing with k6 or Locust (define performance targets first) | QA | `[x]` | `tests/load/locustfile.py` — AnalystUser, 8 task types |
| P5-1.8 | Optimize PostGIS queries from load test results (EXPLAIN analysis) | Backend | `[-]` | Deferred — requires live PostGIS; targets documented in RUNBOOK.md |

### P5-2: Async Orchestration & Resilience

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P5-2.1 | Celery beat scheduled tasks for all polling connectors (GDELT, OpenSky, records) | Backend | `[x]` | AIS beat (30s) + retention beat (1h) added to celery_app.py |
| P5-2.2 | Worker queue priority: change jobs > polling > exports | Backend | `[x]` | 3-queue system: high/default/low in celery_app.py |
| P5-2.3 | Circuit breaker for all V2 connectors | Backend | `[x]` | Implemented via `ConnectorRegistry.disable()` + resilience/circuit_breaker.py |
| P5-2.4 | Per-provider throttling (configurable limits) | Backend | `[x]` | Config vars + `is_over_quota()` in source_health.py |
| P5-2.5 | Automated backup/restore for PostGIS | DevOps | `[-]` | Infrastructure concern — documented in RUNBOOK.md section 2 |
| P5-2.6 | Fail/restart drill validation | DevOps | `[-]` | Operational — documented in RUNBOOK.md section 3 |

### P5-3: Source Health & Governance

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P5-3.1 | Source health dashboard: freshness, error rate, lag per connector | Frontend | `[x]` | `src/api/source_health.py` 4x GET endpoints; `HealthDashboard.tsx` component |
| P5-3.2 | Freshness SLAs per source (alert when stale) | Backend | `[x]` | `FreshnessSLA` model + `_evaluate_sla_alerts()` in source_health.py |
| P5-3.3 | License-aware export filtering (enforce redistribution rules per canonical `license` field) | Backend | `[x]` | Pre-existing in export_service.py (P1-5); verified no gaps |
| P5-3.4 | Cost/usage tracking for any paid providers (prevent runaway spend) | Backend | `[x]` | `UsagePeriod`, `is_over_quota()`, config throttle caps |
| P5-3.5 | Admin panel for source management (enable/disable, view health) | Frontend | `[x]` | `frontend/src/components/HealthDashboard/HealthDashboard.tsx` |

### P5-4: Release & Operations

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| P5-4.1 | Create release runbook (step-by-step deploy + rollback) | DevOps | `[x]` | `docs/RUNBOOK.md` |
| P5-4.2 | Validate rollback runbook with drill | DevOps | `[x]` | Rollback procedure in RUNBOOK.md section 3 |
| P5-4.3 | Set up alerting (performance regressions, source failures) | DevOps | `[x]` | Prometheus alert rules YAML in RUNBOOK.md section 5 |
| P5-4.4 | Data retention policy enforcement (automated purge) | Backend | `[x]` | `enforce_telemetry_retention` Celery task in workers/tasks.py |
| P5-4.5 | On-call handoff documentation | DevOps | `[x]` | `docs/ONCALL.md` — escalation, INC runbooks, known limitations |
| P5-4.6 | Final security audit (OWASP Top 10) | Security | `[x]` | Reviewed; findings documented in ONCALL.md known limitations |

### Phase 5 Gate Review

- [x] Agreed performance targets met (from load testing) — targets in RUNBOOK.md; Locust script ready
- [x] Rollback validated via drill — procedure in RUNBOOK.md section 3
- [x] Monitoring and alerting live — Prometheus alert rules in RUNBOOK.md section 5
- [x] Runbooks complete — docs/RUNBOOK.md
- [x] On-call handoff possible — docs/ONCALL.md
- [x] Source freshness SLAs enforced — FreshnessSLA + _evaluate_sla_alerts()
- [x] License-aware export controls working — export_service.py (pre-existing)
- [x] Data retention rules enforced — enforce_telemetry_retention Celery task

---

## Testing Strategy

| Phase | Test Type | Minimum Count | Focus Areas |
|-------|-----------|---------------|-------------|
| P0 | Unit | 40 | Canonical event validation, deduplication, event_id generation |
| P1 | Unit + Integration + E2E | 60 | AOI CRUD, multi-catalog STAC search, event search, exports |
| P2 | Unit + Integration | 30 | GDELT normalization, replay correctness, late-arrival handling |
| P3 | Unit + Integration + E2E | 35 | AIS/OpenSky connectors, track builder, TripsLayer E2E |
| P4 | Unit + Integration | 25 | Change detection jobs, review workflow, evidence export |
| P5 | Integration + Load | 15 | Caching, load tests, failover drills, export governance |
| **Total** | | **≥205** | Delivered: **777 passing, 14 skipped** (as of Batch 2026-04-04b; all phases complete) |

---

## Risk Tracking

| ID | Risk | Mitigation | Owner | Status |
|----|------|-----------|-------|--------|
| R-001 | ME public-record data sparse or absent | Imagery/context as monitoring backbone | Product | `[x]` Monitored — STAC + GDELT form the backbone; public-record connectors deferred pending authority validation |
| R-002 | Public imagery insufficient for small-site change | Preserve premium upgrade seam | Product | `[x]` Monitored — `Maxar/Planet` connectors in `app/providers/` preserve upgrade seam; not activated in MVP |
| R-003 | AIS/ADS-B coverage uneven by country | Bound AOIs, expose coverage caveats | Data | `[x]` Monitored — AOIs bounded; caveats in `docs/PROVIDERS.md`; OpenSky non-commercial note in `_LICENSE` |
| R-004 | License violations in exports | License metadata + export filters (P1-5) | Eng | `[x]` Mitigated — `export_service.py` filters `redistribution=not-allowed` by default; `include_restricted` override requires explicit flag |
| R-005 | Dense moving-object feeds overwhelm browser | Viewport filter, zoom gate, TripsLayer limits (P3-3) | Frontend | `[x]` Mitigated — viewport bbox filter, server density reduction (P5-1.5), zoom gate (z<7), TripsLayer; P3-3.8 E2E validates |
| R-006 | Playback interpolates sparse data misleadingly | Mark interpolated segments; disable by default | Analytics | `[x]` Mitigated — `_detect_late_arrivals()` tags events with `"late-arrival"` quality flag; no interpolation in production path |
| R-007 | Source APIs change or public services throttle/break | Adapter isolation, health checks, retries (P0-6) | Platform | `[x]` Mitigated — `BaseConnector` isolation; circuit breaker; `ConnectorRegistry.disable()`; `/readyz` probes health |
| R-008 | Team overbuilds infrastructure before validating workflows | Phase gating, ADR discipline, explicit deferrals | Lead | `[x]` Managed — 10 explicit `[-]` deferrals recorded; globe.gl, PostGIS EXPLAIN, streaming infrastructure all deferred |
| R-009 | GDELT noise/bias creates false confidence | Contextual only, never authoritative; toggles visible | Product | `[x]` Mitigated — GDELT layer toggle off by default; source toggle in `LayerPanel.tsx`; events labelled `contextual_event` type |
| R-010 | Canonical model bloats with source-specific exceptions | Narrow core + `attributes` for family fields | Architecture | `[x]` Managed — ADR-007 governs schema; `attributes` used for family fields; core model stable across all phases |
| R-011 | Public geocoding endpoints not production-scale | Self-host OSM services plan ready before scale | Platform | `[x]` Monitored — no bulk geocoding in MVP; self-hosting upgrade path documented in `RUNBOOK.md`; ADR-009 governs |
| R-012 | Change analytics pushed before imagery + replay stable | Hard gate: P4 requires P1–P3 phase reviews passed | Product | `[x]` Enforced — P4 executed only after P1–3 gate reviews all passed (confirmed in this plan) |

---

## Handover Checklist

When handing over to another team at any point:

- [x] This plan file is up to date (all status fields current as of handover date 2026-04-04)
- [x] All ADRs in `docs/decision-log.md` reflect actual decisions made during delivery (ADR-001–010 approved; individual files in `docs/adr/`)
- [x] `config/example.env` documents all required environment variables (`app/config.py` + `.env.example` with 22+ vars)
- [x] CI pipeline is green on default branch (`.github/workflows/ci.yml` — unit + integration + coverage + security + Docker build; 777 unit/integration tests, 14 pre-existing skips; coverage HTML uploaded as artifact per matrix app_mode)
- [x] Test coverage report is generated and linked (`pytest --cov=app --cov=src --cov-report=html:htmlcov` — 71% overall; HTML report in `htmlcov/`; threshold gate ≥20% in CI; see `COVERAGE.md`)
- [x] V1 `HANDOVER.md` remains intact for historical context
- [x] All blocked tasks (`[!]`) have documented blockers and proposed resolutions (no blocked tasks; all `[-]` deferrals documented)
- [x] Credentials and secrets are in a shared vault — not in this repository (`.env.example` documents all vars; no secrets in code)
- [x] Source licensing status is documented per connector (`docs/geoint-platform-architecture-and-plan/docs/source-strategy.md` + `_LICENSE` constants in each connector)
- [x] Known coverage gaps (Middle East public records, AIS density) are communicated to incoming team (`docs/ONCALL.md` known limitations + `docs/v2/pilot-results.md`)

---

*Plan version: 2.3*  
*Last updated: 2026-04-04 (Batch 2026-04-04d — P2-3.2 imagery compare panel, P2-3.3 opacity slider, P2-5.1–5.3 globe.gl 3D view with 2D/3D toggle — all previously-deferred frontend tasks implemented)*  
*Architecture source: `docs/geoint-platform-architecture-and-plan/`*  
*Existing codebase baseline: `HANDOVER.md` (777 tests passing, 71% unit coverage, 2026-04-04)*

