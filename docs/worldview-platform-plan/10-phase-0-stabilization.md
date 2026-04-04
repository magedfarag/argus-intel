# Phase 0 — Stabilization

## Objective

Make the current branch build-clean, data-consistent, and safe to extend.

## Exit criteria

- frontend `tsc -b` passes
- targeted backend tests pass
- app startup smoke test passes
- no dead-end poller write paths remain
- Phase 1 contracts are frozen and documented

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P0-1 | Fix `GlobeView` type and data-shape mismatches | `frontend/src/components/GlobeView/`, `frontend/src/api/types.ts` | `L4` | `[ ]` | — | `P0-A` | Reconcile `bbox`, `last_known_position`, implicit `any`, and unused props |
| P0-2 | Fix worker ingestion path mismatch and dead-end store usage | `app/workers/tasks.py`, `src/api/playback.py`, `src/services/telemetry_store.py` | `L2` + `L3` | `[ ]` | — | `P0-B` | Remove `upsert` mismatch and decide one write path for telemetry/replay |
| P0-3 | Freeze the single-source-of-truth query contract for replay | `src/api/playback.py`, `src/services/` | `L0` + `L3` | `[ ]` | P0-2 | `P0-D` | Produce one documented path for playback data access |
| P0-4 | Add mandatory CI gates for frontend typecheck and targeted pytest | `.github/workflows/ci.yml` | `L6` | `[ ]` | — | `P0-C` | Gate later phase merges |
| P0-5 | Add startup smoke checks for app + seeded demo mode | CI + smoke script | `L6` | `[ ]` | P0-4 | `P0-C` | Catch broken imports/wiring early |
| P0-6 | Re-open stale “complete” items in existing plans where implementation is broken | `MARITIME_PLAN.md`, active docs | `L0` | `[ ]` | P0-1, P0-2 | `P0-D` | Planning hygiene so tracking reflects reality |

## Parallel execution notes

- `P0-1`, `P0-2`, and `P0-4` can start immediately.
- `P0-3` should start once `P0-2` clarifies the storage direction.
- `P0-6` is a closeout task after the branch is green.

## Validation

- run frontend typecheck
- run playback/AIS/OpenSky targeted tests
- start app in demo mode and verify first-load panels render

## Gate review

- [ ] Current branch is build-clean
- [ ] Replay path is not split across incompatible stores
- [ ] CI blocks obvious regressions
- [ ] Phase 1 contract decisions are documented
