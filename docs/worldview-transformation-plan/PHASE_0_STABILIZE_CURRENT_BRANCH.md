# Phase 0: Stabilize Current Branch

## Objective

Make the current ARGUS branch build-clean, type-safe, and internally consistent before new feature expansion.

## Why This Phase Exists

The repo already contains active maritime/globe work, but some of it is incomplete or mismatched with shared types and store paths. Shipping more features on top of this would multiply rework.

See also: [Known Issues Register](./KNOWN_ISSUES.md)

## Entry Criteria

- Current workspace branch is available
- Existing globe, playback, and worker code is in scope

## Exit Criteria

- Frontend typecheck passes
- Core targeted backend tests pass
- Globe overlays compile and use the real shared API types
- Pollers write into stores that the UI and APIs actually consume
- CI catches the same category of regressions going forward

## Track A: Frontend Stabilization

- `[x]` Fix type errors in `frontend/src/components/GlobeView/GlobeView.tsx` — `tsc --noEmit` exits clean
- `[x]` Replace invalid `bbox` assumptions with the actual `geometry` and `centroid` contract from chokepoints — verified in GlobeView.tsx
- `[x]` Replace invalid `last_known_position` assumptions with `last_known_lon` and `last_known_lat` — verified in GlobeView.tsx
- `[x]` Remove or properly use unused `baseStyle` paths in the globe component — removed from `Props` interface, function destructuring, and `App.tsx` call site; `tsc --noEmit` exits clean
- `[x]` Add a small targeted component test or smoke test for globe overlay rendering — **done**: vitest 2.1.9 installed; jsdom environment configured; `src/components/GlobeView/__tests__/GlobeView.smoke.test.tsx` (2 tests: module exports a function, renders without throwing); `pnpm test` exits clean (1 file, 2 passed).

## Track B: Worker And Store Stabilization

- `[x]` Audit `app/workers/tasks.py` for dead-end writes and incorrect store usage — completed
- `[x]` Fix `TelemetryStore` ingestion calls to use the real store interface — `store.upsert()` → `store.ingest_batch()` in all tasks
- `[ ]` Ensure pollers can feed the same replay/query path used by the frontend — **deferred to Phase 1 Track C** (unified query contract)
- `[ ]` Document the current split between `EventStore` and `TelemetryStore` — **deferred to Phase 1 Track A** (schema/contract freeze)
- `[x]` Remove or mark any temporary demo-only ingestion shortcuts — annotated 4 shortcuts in `app/workers/tasks.py`: GDELT, OpenSky, and AISStream pollers discard normalized events without persisting to EventStore; `enforce_telemetry_retention` operates on in-memory store only

## Track C: CI And Quality Gates

- `[x]` Add frontend typecheck to CI — `typecheck` job added to `.github/workflows/ci.yml`
- `[x]` Add a backend startup smoke check — `tests/unit/test_startup_smoke.py` (2 tests)
- `[x]` Add targeted tests for globe data contract mismatches — `tests/unit/test_globe_api_contract.py` (2 tests, endpoints `/api/v1/chokepoints` and `/api/v1/dark-ships`)
- `[x]` Add targeted tests for telemetry ingestion paths — `TestTelemetryStoreInterfaceContract` added to `tests/unit/test_telemetry_store.py`
- `[x]` Update handoff or README notes if known gaps are closed — Phase 0 status section (§13) added to HANDOVER.md (2026-04-04)

## Suggested Subagent Split

- Subagent 1: Track A
- Subagent 2: Track B
- Subagent 3: Track C

## Integration Notes

- Merge Track B before final Track A validation if API shape changes.
- Do not start Phase 1 implementation until this phase is closed.
