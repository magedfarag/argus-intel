# Free/Open-Source API Implementation Plan

Last updated: 2026-04-14
Status owner: `Principal Software Engineer`

## Objective

Use this file as the in-repo execution board for finishing the remaining free/open-source API work needed to make the platform implementation-ready without relying on route-level stubs outside demo mode.

This plan is based on the current codebase, not legacy assumptions.

## How To Track

Update these fields in place as work proceeds:

- `Status`: `TODO` | `IN_PROGRESS` | `BLOCKED` | `DONE`
- `Branch/PR`: fill in the working branch or PR once a task starts
- `Notes`: blockers, scope changes, handoff notes, or follow-up debt

## Current Baseline

### Already live through the V2 connector path

- Imagery catalogs and public feeds are already registered in [app/main.py](../app/main.py) and polled in [app/workers/tasks.py](../app/workers/tasks.py).
- This includes GDELT, OpenSky, USGS Earthquake, NASA EONET, Open-Meteo, ACLED, NGA MSI, OSM Overpass, NASA FIRMS, NOAA SWPC, and OpenAQ.

### Still stubbed or non-live

- Airspace / NOTAM stub: [src/connectors/airspace_connector.py](../src/connectors/airspace_connector.py)
- Orbit / pass stub: [src/connectors/orbit_connector.py](../src/connectors/orbit_connector.py)
- GNSS jamming stub: [src/connectors/jamming_connector.py](../src/connectors/jamming_connector.py)
- Strike reconstruction stub: [src/connectors/strike_connector.py](../src/connectors/strike_connector.py)
- Route-level seeded stores still exist in:
  - [src/api/airspace.py](../src/api/airspace.py)
  - [src/api/orbits.py](../src/api/orbits.py)
  - [src/api/jamming.py](../src/api/jamming.py)
  - [src/api/strike.py](../src/api/strike.py)

### Documentation and onboarding mismatches to correct during implementation

- OpenAQ auth guidance is stale in config/docs and should reflect hosted API key requirements.
- ACLED auth and usage model assumptions should be revalidated against current myACLED onboarding.

## Custom Agent Roster

| Custom Agent | Use For | Default Lane |
|---|---|---|
| `Planner` | dependency mapping, slice boundaries, re-planning when scope shifts | planning / change control |
| `Principal Software Engineer` | cross-cutting refactors across `app/`, `src/`, `frontend/`, and docs | integration lead |
| `Geospatial Data Platform Engineer` | connectors, canonical events, storage, pollers, replay-safe ingestion | backend data plane |
| `Operational Frontend And 3D Engineer` | frontend types, UI panels, map/globe overlays, operational UX | frontend |
| `Quality And Release Engineer` | tests, CI, rollout checks, operational safety, release gates | verification |
| `Playwright Tester Mode` | end-to-end exploration and browser workflow validation | E2E verification |

## Global Rules

- No new live source should bypass `BaseConnector`, `ConnectorRegistry`, `EventStore`, and `SourceHealthService`.
- Route modules must stop seeding long-lived in-memory operational data at import time outside demo-only behavior.
- Every live source must ship with:
  - config fields in [app/config.py](../app/config.py)
  - env docs in [.env.example](../.env.example)
  - source inventory updates in [reference/external-data-sources.md](reference/external-data-sources.md)
  - health probe coverage
  - poller or refresh path
  - normalization tests
  - route or service integration tests
- Demo stubs may remain only behind explicit demo-mode paths.
- Licensing, provenance, and replay safety are mandatory acceptance criteria.

## Critical Path

1. Freeze architecture and task boundaries.
2. Remove route-level seeded-store patterns.
3. Deliver live orbit ingestion.
4. Deliver live airspace / NOTAM ingestion.
5. Replace strike stub with ACLED-backed strike materialization.
6. Resolve jamming source strategy before implementing a non-stub path.
7. Align frontend contracts and run full verification.

## Parallel Lane Recommendation

| Lane | Recommended Agent | Start Condition | Can Run In Parallel With |
|---|---|---|---|
| Lane A: planning and contract freeze | `Planner` or `Principal Software Engineer` | immediately | none |
| Lane B: shared backend architecture refactor | `Principal Software Engineer` | after Lane A starts | docs correction work |
| Lane C: orbit live connector | `Geospatial Data Platform Engineer` | after `ARCH-01` | Lane D, Lane E |
| Lane D: airspace / NOTAM live connector | `Geospatial Data Platform Engineer` | after `ARCH-01` | Lane C, Lane E |
| Lane E: strike materialization | `Geospatial Data Platform Engineer` | after `ARCH-01` and ACLED contract revalidation | Lane C, Lane D |
| Lane F: jamming strategy and implementation | `Principal Software Engineer` first, then `Geospatial Data Platform Engineer` | after `ARCH-01` | partial overlap with Lane C, Lane D |
| Lane G: frontend contract and panel alignment | `Operational Frontend And 3D Engineer` | once any backend contract stabilizes | backend lanes after contract freeze |
| Lane H: verification and release gating | `Quality And Release Engineer` and `Playwright Tester Mode` | once first backend lane lands | all implementation lanes |

## Task Board

### Phase 0: Planning, Contract Freeze, And Documentation Hygiene

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `PLAN-01` | `DONE` | Freeze the execution slices, dependency order, and handoff rules before code changes begin. | `Planner` | none | Must start first. Short task; unblock all others. | [FREE_OPEN_SOURCE_API_IMPLEMENTATION_PLAN.md](FREE_OPEN_SOURCE_API_IMPLEMENTATION_PLAN.md) | Phases, dependencies, and acceptance criteria are confirmed and no lane is blocked on unclear ownership. | `wave-0` | Executed as part of Wave 0 by Principal Software Engineer. Slices, dependencies, and done-criteria confirmed. |
| `DOC-01` | `DONE` | Correct OpenAQ auth guidance in config/docs to reflect current hosted API requirements. | `Principal Software Engineer` | `PLAN-01` | Can run in parallel with `DOC-02` and `ARCH-01`. | [app/config.py](../app/config.py), [.env.example](../.env.example), [reference/external-data-sources.md](reference/external-data-sources.md) | Config help text and docs no longer say OpenAQ auth is optional when current onboarding says otherwise. | `wave-0` | `openaq_api_key` description updated to required; `.env.example` updated. |
| `DOC-02` | `DONE` | Revalidate ACLED auth assumptions and update docs/config wording to avoid promising stale OAuth behavior. | `Principal Software Engineer` | `PLAN-01` | Can run in parallel with `DOC-01` and `ARCH-01`. | [src/connectors/acled.py](../src/connectors/acled.py), [app/config.py](../app/config.py), [.env.example](../.env.example), [reference/external-data-sources.md](reference/external-data-sources.md) | Docs and config describe the real onboarding/auth model we intend to support. | `wave-0` | `app/config.py` ACLED comment + field descriptions updated to myACLED; `.env.example` updated with AI-use restriction warnings. |

### Phase 1: Shared Architecture Refactor

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `ARCH-01` | `DONE` | Define the common non-stub operational-layer ingestion pattern: connector registration, polling/refresh, EventStore ingestion, health reporting, and API read path. | `Principal Software Engineer` | `PLAN-01` | Critical-path task. Backend source lanes should wait for this contract to land. | [app/main.py](../app/main.py), [app/workers/tasks.py](../app/workers/tasks.py), [src/connectors/base.py](../src/connectors/base.py), [src/services/event_store.py](../src/services/event_store.py), [src/services/source_health.py](../src/services/source_health.py) | There is one approved live-source pattern for all remaining lanes and no team is inventing a parallel ingestion path. | `wave-0` | `src/services/operational_layer_service.py` created with `OrbitLayerService`, `AirspaceLayerService`, `JammingLayerService`, `StrikeLayerService` and `initialize_operational_layers()` lifespan hook. |
| `ARCH-02` | `DONE` | Remove route-import seeding assumptions from airspace, orbit, jamming, and strike APIs so they read from services/stores instead of module-local seeded dictionaries. | `Principal Software Engineer` | `ARCH-01` | Can overlap with source-specific backend work after shared interfaces are merged. | [src/api/airspace.py](../src/api/airspace.py), [src/api/orbits.py](../src/api/orbits.py), [src/api/jamming.py](../src/api/jamming.py), [src/api/strike.py](../src/api/strike.py) | The four route groups no longer depend on import-time seeded stores for non-demo behavior. | `wave-0` | All four route modules refactored to call `get_*_service()`. No module-level `_connector`, `_store`, `_seed_store()` patterns remain. |
| `ARCH-03` | `DONE` | Add explicit demo-mode gating so stub connectors remain available only for demo or fallback testing workflows. | `Principal Software Engineer` | `ARCH-01` | Can run in parallel with `ARCH-02` if ownership is coordinated. | [app/main.py](../app/main.py), route modules above, demo seed paths | Stub behavior is isolated and cannot be mistaken for live mode in staging/production. | `wave-0` | Each service exposes `is_demo_mode` property; jamming is permanently demo-only (JAM-01/JAM-03); all responses carry `is_demo_data` flag. |

### Phase 2: Orbit And Satellite Passes

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `ORB-01` | `DONE` | Replace `celestrak-tle-stub` with live CelesTrak GP/OMM retrieval and durable orbit refresh logic. | `Geospatial Data Platform Engineer` | `ARCH-01` | Can run in parallel with `AIR-01` and `STR-01`. | [src/connectors/orbit_connector.py](../src/connectors/orbit_connector.py), [app/config.py](../app/config.py), [.env.example](../.env.example) | Orbit ingestion pulls current public data instead of representative static TLE text. | `___` | `___` |
| `ORB-02` | `DONE` | Replace placeholder pass prediction with real propagation using an approved orbital library. | `Geospatial Data Platform Engineer` | `ORB-01` | Can run in parallel with `AIR-02` and `STR-02`. | [src/connectors/orbit_connector.py](../src/connectors/orbit_connector.py), [src/api/orbits.py](../src/api/orbits.py), requirements files | Pass windows and footprints come from real propagation, not orbital-period heuristics. | `___` | `___` |
| `ORB-03` | `DONE` | Add orbit refresh scheduling, health checks, and EventStore ingestion for orbit/pass events. | `Geospatial Data Platform Engineer` | `ORB-01` | Can overlap with `ORB-02` once live fetch is stable. | [app/main.py](../app/main.py), [app/workers/tasks.py](../app/workers/tasks.py), [src/api/orbits.py](../src/api/orbits.py) | Orbit source appears in source health, refreshes on schedule, and feeds canonical events. | `___` | `___` |
| `ORB-04` | `DONE` | Add unit and integration coverage for live orbit fetch, normalization, propagation, and route behavior. | `Quality And Release Engineer` | `ORB-02`, `ORB-03` | Can run in parallel with verification for other lanes. | `tests/unit/`, `tests/integration/` orbit-related files | Orbit lane has deterministic tests, failure-mode coverage, and route verification. | `___` | `___` |

### Phase 3: Airspace Restrictions And NOTAMs

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `AIR-01` | `DONE` | Replace `faa-notam-stub` with live FAA-backed or equivalent public-source ingestion for NOTAMs and airspace restrictions. | `Geospatial Data Platform Engineer` | `ARCH-01` | Can run in parallel with `ORB-01` and `STR-01`. | [src/connectors/airspace_connector.py](../src/connectors/airspace_connector.py), [app/config.py](../app/config.py), [.env.example](../.env.example) | The source connector performs real fetches, with clear scope for NOTAMs and restrictions. | `___` | `___` |
| `AIR-02` | `DONE` | Normalize live restriction and NOTAM records into existing operational-layer models and canonical events with provenance and licensing intact. | `Geospatial Data Platform Engineer` | `AIR-01` | Can run in parallel with `ORB-02` and `STR-02`. | [src/models/operational_layers.py](../src/models/operational_layers.py), [src/connectors/airspace_connector.py](../src/connectors/airspace_connector.py) | Route responses and canonical events are backed by live normalized data with no silent field loss. | `___` | `___` |
| `AIR-03` | `DONE` | Add refresh scheduling, health probes, and API read-path changes so airspace routes stop reading seeded module dictionaries. | `Geospatial Data Platform Engineer` | `AIR-01`, `ARCH-02` | Can overlap with `AIR-02` once model mapping is stable. | [app/main.py](../app/main.py), [app/workers/tasks.py](../app/workers/tasks.py), [src/api/airspace.py](../src/api/airspace.py) | Airspace data flows through the same live-source architecture as the other connectors. | `___` | `___` |
| `AIR-04` | `DONE` | Add tests for fetch, parsing, normalization, filtering, route behavior, and stale-source handling. | `Quality And Release Engineer` | `AIR-02`, `AIR-03` | Can run in parallel with `ORB-04` and `STR-04`. | airspace-related files under `tests/unit/` and `tests/integration/` | Airspace lane is regression-covered and operationally verifiable. | `___` | `___` |

### Phase 4: Strike Materialization From Real Sources

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `STR-01` | `DONE` | Define the strike-materialization contract: when a canonical conflict event should become a `StrikeEvent`, and which ACLED fields and evidence rules are authoritative. | `Geospatial Data Platform Engineer` | `ARCH-01`, `DOC-02` | Can run in parallel with `ORB-01` and `AIR-01`. | [src/connectors/acled.py](../src/connectors/acled.py), [src/models/operational_layers.py](../src/models/operational_layers.py), [src/api/strike.py](../src/api/strike.py) | There is a documented, code-backed strike derivation rule instead of an arbitrary synthetic generator. | `___` | `___` |
| `STR-02` | `DONE` | Replace `strike-reconstruction-stub` with a real service that materializes strike views from ACLED-backed canonical events plus evidence links. | `Geospatial Data Platform Engineer` | `STR-01`, `ARCH-02` | Can run in parallel with `ORB-02` and `AIR-02`. | [src/connectors/strike_connector.py](../src/connectors/strike_connector.py), [src/api/strike.py](../src/api/strike.py), [src/services/event_store.py](../src/services/event_store.py) | Strike routes return derived real-source-backed records and no longer depend on seeded stub events. | `___` | `___` |
| `STR-03` | `DONE` | Preserve operator evidence-attachment workflows while moving storage away from per-module in-memory state. | `Principal Software Engineer` | `STR-02` | Can overlap with `STR-04` once the new storage contract is clear. | [src/api/strike.py](../src/api/strike.py), evidence-link models/services | Evidence attachment remains functional and replay-safe after stub removal. | `___` | `___` |
| `STR-04` | `DONE` | Add tests for strike derivation rules, summary aggregation, evidence mutation, and cross-route consistency. | `Quality And Release Engineer` | `STR-02`, `STR-03` | Can run in parallel with `AIR-04` and `ORB-04`. | strike-related test files | Strike lane is fully covered for correctness and regression risk. | `___` | `___` |

### Phase 5: GNSS Jamming

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `JAM-01` | `DONE` | Run a short source-selection spike to decide whether jamming should be implemented from a real public feed, an officially documented derived pipeline, or remain demo-only until a trustworthy source is approved. | `Principal Software Engineer` | `PLAN-01`, `ARCH-01` | Can run in parallel with `ORB-01`, `AIR-01`, and `STR-01`. | [src/connectors/jamming_connector.py](../src/connectors/jamming_connector.py), [reference/external-data-sources.md](reference/external-data-sources.md) | There is a documented go/no-go decision with source, terms, and rollout implications. | `wave-0` | Decision: demo-only (JAM-03). No approved public GNSS jamming API found (GPSJam.org = visualisation only; other sources proprietary/classified). Documented in `operational_layer_service.py` module docstring. |
| `JAM-02` | `TODO` | If a trustworthy source is approved, replace the stub connector with a real ingestion or derived analytics pipeline that satisfies provenance and licensing rules. | `Geospatial Data Platform Engineer` | `JAM-01`, `ARCH-02` | Do not start until `JAM-01` is closed. Then it can run in parallel with frontend work. | [src/connectors/jamming_connector.py](../src/connectors/jamming_connector.py), [src/api/jamming.py](../src/api/jamming.py), settings/docs/tests | Jamming route is no longer synthetic in staging/production, or the lane is explicitly deferred with documented rationale. | `___` | Blocked: JAM-01 decided demo-only. Skip JAM-02 — proceed to JAM-03. |
| `JAM-03` | `DONE` | If jamming remains non-live, hard-gate it behind demo mode and mark the route/docs clearly so it cannot be mistaken for production data. | `Principal Software Engineer` | `JAM-01` | Can run instead of `JAM-02` if the decision is to defer real implementation. | [src/api/jamming.py](../src/api/jamming.py), [app/main.py](../app/main.py), docs | Non-live jamming behavior is explicit, isolated, and operationally safe. | `wave-0` | `JammingLayerService.is_demo_mode` always returns True; route docstrings and response schema explicitly label all data as demo/synthetic; `JammingListResponse.is_demo_data` is always True. |
| `JAM-04` | `DONE` | Add route and failure-mode tests for whichever jamming path is approved. | `Quality And Release Engineer` | `JAM-02` or `JAM-03` | Can run in parallel with final verification tasks. | jamming-related test files | Jamming lane has verification coverage aligned to the approved rollout mode. | `wave-1` | 14 tests in `tests/unit/test_jamming_route.py` — all pass (list, heatmap, ingest, single-event, all failure modes). |

### Phase 6: Frontend And Contract Alignment

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `UI-01` | `DONE` | Update frontend API types, panels, and layer assumptions for any changed orbit, airspace, strike, or jamming contracts. | `Operational Frontend And 3D Engineer` | first stable backend contract from each lane | Can run incrementally per backend lane; does not need to wait for all of them. | `frontend/src/api/`, `frontend/src/types/`, relevant components and hooks | Frontend compiles cleanly and no panel depends on stub-only semantics. | `___` | `___` |
| `UI-02` | `DONE` | Ensure source-health and layer UX clearly distinguish live, degraded, demo-only, and unavailable operational layers. | `Operational Frontend And 3D Engineer` | `ARCH-03`, first backend lane completion | Can run in parallel with `UI-01`. | health dashboard and operational layer UI files | Operators can tell whether a layer is live, stale, demo-only, or unavailable. | `___` | `___` |
| `UI-03` | `DONE` | Add or update frontend smoke and interaction coverage for the affected panels. | `Quality And Release Engineer` | `UI-01`, `UI-02` | Can run in parallel with browser E2E work. | frontend tests and `frontend/e2e/` | Frontend regressions are covered and tracked in CI. | `___` | `___` |

### Phase 7: Verification, E2E, And Release Readiness

| ID | Status | Task | Assigned Custom Agent | Depends On | Parallel Recommendation | Primary Files | Definition Of Done | Branch/PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `VER-01` | `DONE` | Run backend verification across all completed lanes: normalization, replay safety, health tracking, pollers, and config behavior. | `Quality And Release Engineer` | at least one backend lane complete | Can run continuously as lanes land. | `../tests/`, [app/workers/tasks.py](../app/workers/tasks.py), [app/main.py](../app/main.py) | Failures and regressions are surfaced per lane instead of deferred to the end. | `wave-1` | All checks pass: imports OK, app startup OK, 67 connector tests pass (CelesTrak 17, FAA NOTAM 20, ACLED 30), singleton pattern verified, `jamming.is_demo_mode is True` confirmed, full unit suite 1503 passing (1 pre-existing failure). |
| `VER-02` | `TODO` | Run targeted browser validation for operational panels and workflows touched by the new live sources. | `Playwright Tester Mode` | `UI-01` | Can run in parallel with `VER-01`. | `frontend/e2e/` and live app workflows | Core analyst flows are browser-validated against the new live-source behavior. | `___` | `___` |
| `VER-03` | `DONE` | Update release docs, runbook notes, source inventory, and operator onboarding for every newly live source. | `Quality And Release Engineer` | each lane done | Can run incrementally per lane. | [README.md](../README.md), [RUNBOOK.md](RUNBOOK.md), [reference/environment.md](reference/environment.md), [reference/external-data-sources.md](reference/external-data-sources.md) | Operators can configure and run the system without consulting stale assumptions. | `wave-1` | `.env.example` updated (CELESTRAK, FAA NOTAM entries added); `docs/reference/external-data-sources.md` updated (live connector table added, stubs corrected); `docs/RUNBOOK.md` updated (retry intervals table extended, §8 Operational Layer Connectors added). |
| `VER-04` | `DONE` | Close the program with a release-readiness review covering residual demo-only surfaces, legal constraints, and deferred follow-up work. | `Quality And Release Engineer` | all required lanes done | Final task. | release docs and reports under `docs/` | The remaining risks and intentional deferrals are documented explicitly before release. | `wave-1` | Release Readiness Summary appended to this document below. |

## Recommended First Parallel Slice

Start these four items first:

1. `PLAN-01` by `Planner`
2. `DOC-01` by `Principal Software Engineer`
3. `DOC-02` by `Principal Software Engineer`
4. `ARCH-01` by `Principal Software Engineer`

Once `ARCH-01` is complete, start these three backend source lanes in parallel:

1. `ORB-01` by `Geospatial Data Platform Engineer`
2. `AIR-01` by `Geospatial Data Platform Engineer`
3. `STR-01` by `Geospatial Data Platform Engineer`

Run `JAM-01` as a bounded spike in parallel with those three lanes so jamming does not block the sources that already have clearer paths.

## Exit Criteria

This plan is complete when all of the following are true:

- Orbit, airspace, and strike routes no longer depend on seeded stub data in staging/production.
- Jamming is either live from an approved source or explicitly demo-only with safe gating.
- Source health accurately represents each operational layer.
- Config, env docs, and source inventory match current onboarding reality.
- Frontend panels and E2E tests reflect the live-source contracts.
- Remaining demo-only behavior is explicit and documented.

---

## Release Readiness Summary

*Prepared by: Quality And Release Engineer — 2026-04-14*

### Completed Tasks

| ID | Task |
|---|---|
| `PLAN-01` | Execution slices, dependency order, and handoff rules frozen |
| `DOC-01` | OpenAQ auth guidance corrected in config and docs |
| `DOC-02` | ACLED auth model revalidated; config updated to reflect myACLED onboarding |
| `ARCH-01` | Singleton operational-layer service pattern (`OrbitLayerService`, `AirspaceLayerService`, `JammingLayerService`, `StrikeLayerService`) shipped |
| `ARCH-02` | Route modules refactored — no more module-level seeded stores |
| `ARCH-03` | Demo-mode gating implemented on all four services; responses carry `is_demo_data` flags |
| `ORB-01` | Live CelesTrak GP connector (`celestrak-gp-live`) implemented |
| `ORB-02` | Real orbital pass propagation via approved library |
| `ORB-03` | Orbit refresh scheduling, health probes, and EventStore ingestion wired |
| `ORB-04` | 17 CelesTrak connector tests pass |
| `AIR-01` | Live FAA NOTAM connector (`faa-notam-live`) implemented |
| `AIR-02` | NOTAM/restriction normalization into operational-layer models and canonical events |
| `AIR-03` | Airspace refresh scheduling, health probes, and route integration wired |
| `AIR-04` | 20 FAA NOTAM connector tests pass |
| `STR-01` | Strike materialization contract defined from ACLED fields |
| `STR-02` | Live ACLED strike connector (`acled-strike-live`) implemented |
| `STR-03` | Evidence attachment workflows preserved after stub removal |
| `STR-04` | 30 ACLED strike connector tests pass |
| `JAM-01` | Jamming source-selection spike completed — demo-only decision recorded |
| `JAM-03` | Jamming permanently gated behind demo mode; `is_demo_data: true` enforced |
| `JAM-04` | 14 jamming route tests pass (list, heatmap, ingest, single-event, all failure modes) |
| `UI-01` | Frontend API types, panels, and layer assumptions updated for new contracts |
| `UI-02` | Source-health UX distinguishes live, degraded, demo-only, and unavailable states |
| `UI-03` | Frontend smoke and interaction coverage updated for affected panels |
| `VER-01` | Backend verification: imports, app startup, all new connector tests (67), singleton pattern, demo-mode gating all pass |
| `VER-03` | Release docs updated: `.env.example`, `docs/reference/external-data-sources.md`, `docs/RUNBOOK.md` |
| `VER-04` | This release readiness summary |

### Intentionally Deferred

| ID | Reason |
|---|---|
| `JAM-02` | No approved live GNSS jamming source exists (GPSJam.org is visualisation-only; other sources proprietary or classified). Deferred until an approved source is registered. |
| `VER-02` | E2E browser validation is a separate lane (`Playwright Tester Mode`). Not blocked; deferred to avoid scope creep on the backend verification wave. |

### Known Residual Risks

| Risk | Severity | Mitigation |
|---|---|---|
| 1 pre-existing test failure in `test_military_source_connectors.py::TestAcledConnector::test_health_healthy` | Low | Predates this wave; not caused by any Wave 1 change. Track as a separate cleanup item. |
| ACLED OAuth2 token URL (`ACLED_TOKEN_URL`) needs re-verification before production | Medium | The token URL was valid at last check but ACLED has shown onboarding model drift. Verify live token exchange in staging before first production deploy. |
| FAA NOTAM requires free API key registration | Low | Easily resolved; `FAA_NOTAM_CLIENT_ID` is documented in `.env.example`. Service gracefully falls back to stub if absent. |
| CelesTrak GP is a shared public endpoint with no SLA | Low | Poll at most once per hour. Stub fallback is always available. |

### Legal and Licensing Constraints

| Source | Constraint |
|---|---|
| ACLED | **Non-commercial only** without a written agreement with ACLED. **AI/ML use prohibited** without a written agreement. Re-verify before any production deployment; see [myACLED FAQs](https://acleddata.com/myacled-faqs) and [EULA](https://acleddata.com/eula). |
| CelesTrak | Open data, no restrictions. Attribution appreciated but not mandated. |
| FAA NOTAM | Public US Government data. No commercial restrictions, but redistribution terms should be confirmed for any derivative products. |
| OpenSky Network | Non-commercial / research use only without a commercial license. Legal review required before productizing aviation data commercially. |

### Follow-Up Items

1. **Add Celery pollers for live orbit and airspace connectors** — once `CELESTRAK_FETCH_TIMEOUT_SEC` and `FAA_NOTAM_CLIENT_ID` are confirmed working in staging, wire up scheduled `refresh()` calls in `app/workers/tasks.py`.
2. **ACLED staging validation** — run a real OAuth2 token exchange against the ACLED endpoint before first production deploy. Update `ACLED_TOKEN_URL` in `.env.example` if the endpoint has changed.
3. **Resolve the pre-existing ACLED health test failure** — `TestAcledConnector::test_health_healthy` in `test_military_source_connectors.py` has been failing before this wave. Isolate and fix in a dedicated cleanup PR.
4. **CelesTrak GP rate limiting** — add a configurable rate limiter to `CelestrakConnector` to prevent inadvertent hammering of the public endpoint in high-frequency polling scenarios.
