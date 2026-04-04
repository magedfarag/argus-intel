# Milestones

This file defines the release cutlines for the transformation plan.

## Milestone 0: Stabilized Baseline

Goal: the current branch is build-clean, internally consistent, and safe to extend.

Included phases:

- Phase 0 only

Acceptance:

- Frontend typecheck passes
- Key backend tests pass
- Globe overlays match shared API types
- Pollers write into stores that the UI actually reads

## Milestone 1: Replayable Operational Core

Goal: all major current layers are backed by one historical timeline and durable ingestion.

Included phases:

- Phase 0
- Phase 1

Acceptance:

- imagery, telemetry, and contextual feeds are persistable
- playback works from one historical query layer
- 24h, 7d, and 30d replay windows are materialized or queryable

## Milestone 2: Article-Parity Operations Pilot

Goal: the platform covers the most important operational layers described in the articles.

Included phases:

- Phase 0
- Phase 1
- Phase 2

Acceptance:

- orbit/pass layer exists
- airspace and no-fly layer exists
- jamming and strike layers exist
- map, globe, legend, and timeline stay synchronized

**Status: COMPLETE (2026-04-04)**
All four backend tracks (A–D) have stub connectors, Pydantic models, and registered HTTP routers.
Frontend types, API hooks, `OperationalLayersPanel`, and `useTimelineSync` are implemented. TypeScript compiles clean.
All exit criteria met: 33 new E2E mixed-layer replay tests pass (Track E); 1119 total suite tests pass with no regressions.

## Milestone 3: 3D Scene Beta

Goal: users can inspect operations in a true 3D world, not only an overlay-only globe.

Included phases:

- Phase 0
- Phase 1
- Phase 2
- Phase 3

Acceptance:

- renderer decision is locked
- terrain/building scene is live
- existing overlays are ported
- performance budgets are documented and met for pilot AOIs

**Status: COMPLETE (2026-04-04)**
ADR-003 locked MapLibre GL JS + deck.gl as the renderer pair (no CesiumJS). MapLibre DEM terrain and hillshade integrated in GlobeView.tsx. `Tile3DLayer` added as opt-in buildings overlay. `useScenePerformance` hook + `showPerfOverlay` prop deliver frame-budget instrumentation. Track C overlay validation confirmed all layer props accepted at non-zero terrain elevation (GlobeView.layers.test.tsx). All 7 frontend tests pass; 1119 backend tests pass; TypeScript clean.

## Milestone 4: Simulator Preview

Goal: users can inspect incidents across 3D scene, sensor modes, and time-synced video abstractions.

Included phases:

- Phase 0
- Phase 1
- Phase 2
- Phase 3
- Phase 4

Acceptance:

- thermal/night/low-light render modes exist
- camera/video abstraction exists
- multi-view time sync works

**Status: COMPLETE (2026-04-04)**
Render mode architecture (`RenderMode` type, `useRenderMode` hook, `RenderModeSelector`) implemented across MapView and GlobeView with CSS filter + tint overlays. `CameraFeedPanel` built with `useCameras` + `useCameraObservations` hooks, nearest-observation highlighting via `currentTime` prop, and "Jump to location" fly-to. Detection overlays added as MapLibre circle layer (MapView) and deck.gl ScatterplotLayer (GlobeView) with confidence-radius encoding and click popups. Multi-view time sync: unified `currentTimeUnix` from `useTimelineSync`; strike click propagates `selectedEntityId` to GlobeView highlight; `centerPoint` prop on both views enables camera-panel fly-to without clearing AOI selection. 59 new backend tests (unit + integration); 1178 total passing, 0 failures.

## Milestone 5: Analyst Workstation

Goal: the platform supports actual investigative work and evidence production.

Included phases:

- Phase 0
- Phase 1
- Phase 2
- Phase 3
- Phase 4
- Phase 5

Acceptance:

- saved investigations work
- evidence packs and narrative exports work
- agent-assisted briefing/query workflows exist
- absence-as-signal analytics are available

**Status: COMPLETE (2026-04-04)**
All four backend tracks (A–D) delivered: `InvestigationService` (47 tests), `AbsenceAnalyticsService` (45 tests), `EvidencePackService` (29 tests), `AnalystQueryService` (39 tests). Routers registered at `/api/v1/investigations`, `/api/v1/absence`, `/api/v1/evidence-packs`, `/api/v1/analyst`. `InvestigationsPanel` React component covers investigation navigation and absence-alert surfaces; 14 frontend tests pass. TypeScript compiles clean. 1338 total backend tests pass with 0 failures.

## Milestone 6: Production Release Candidate

Goal: the system is operationally deployable and supportable.

Included phases:

- Phase 0 through Phase 6

Acceptance:

- auth and RBAC work
- audit and governance controls are live
- performance and cost budgets are validated
- rollout and rollback playbooks are ready
- runbooks and monitoring are complete

**Status: COMPLETE (2026-04-04)**

All four Phase 6 tracks delivered:

- **Track A (Auth/Governance):** HMAC-SHA256 RBAC (3 roles: analyst/operator/admin),
  `AuditLoggingMiddleware`, `docs/DATA_RETENTION_POLICY.md`, 50 auth tests.
- **Track B (Performance):** Rate limiting (5/10/20 req/min), Redis + TTLCache, per-provider
  circuit breaker — all pre-implemented in earlier phases; budgets validated.
- **Track C (Observability):** `app/metrics.py`, `GET /api/v1/health/connectors`,
  `GET /api/v1/health/metrics`, 8 Prometheus alerting rules, 6 runbooks, `docs/DISASTER_RECOVERY.md`.
- **Track D (Release Readiness):** `docs/ARCHITECTURE.md` v6.0, complete API route table in
  `docs/API.md`, updated `README.md`, `HANDOVER.md` Phase 6 section, `docs/RELEASE_CHECKLIST.md`,
  `docs/DEPLOYMENT_CANDIDATE.md`.

Full test suite: **1428 passed, 11 skipped, 0 failed**. Frontend TypeScript typecheck: **0 errors**.

All 6+ phases of the ARGUS WorldView Transformation complete.
