# Phase 1 — Historical Data Plane

## Objective

Create one durable historical timeline across imagery, telemetry, and contextual feeds.

## Exit criteria

- raw payloads and normalized events are persisted for supported feeds
- replay works from stored data for 24h, 7d, and 30d windows
- frontend playback no longer depends on demo-only seed data for core scenarios
- schema extensions required for later phases are frozen

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P1-1 | Extend canonical event model for future layer families | `src/models/canonical_event.py`, `frontend/src/api/types.ts` | `L0` + `L1` | `[ ]` | P0-3 | `P1-A` | Add `satellite_orbit`, `satellite_pass`, `airspace_restriction`, `gps_jamming_event`, `strike_event`, `camera_observation` |
| P1-2 | Define snapshot persistence contract for volatile feeds | `src/storage/`, object storage layout | `L1` | `[ ]` | P0-3 | `P1-A` | Raw payload path, retention tags, provenance contract |
| P1-3 | Build unified ingestion write path for AIS/OpenSky/GDELT/imagery | `src/connectors/`, `app/workers/tasks.py`, `src/normalization/` | `L2` | `[ ]` | P1-1, P1-2 | `P1-B` | One normalize -> persist pipeline |
| P1-4 | Implement a single replay/query service over persisted events | `src/api/playback.py`, `src/services/` | `L3` | `[ ]` | P1-1, P1-3 | `P1-C` | Replace mixed `EventStore` / `TelemetryStore` behavior with one query contract |
| P1-5 | Add materialized replay windows and backfill fixtures | `src/services/`, storage jobs | `L3` + `L1` | `[ ]` | P1-4 | `P1-C` | Support 24h/7d/30d windows and deterministic test fixtures |
| P1-6 | Rewire frontend playback and panels to persisted APIs | `frontend/src/hooks/`, `frontend/src/components/` | `L4` | `[ ]` | P1-4 | `P1-D` | Preserve current UX while switching data sources |
| P1-7 | Add validation for retention, provenance, and replay correctness | `tests/`, CI | `L6` | `[ ]` | P1-3, P1-5, P1-6 | `P1-D` | Include late-arrival and replay window tests |

## Parallel execution notes

- `P1-1` and `P1-2` should be the first contract freeze.
- `P1-3` and `P1-4` can then run in parallel with a strict handoff on persisted model shape.
- `P1-6` should consume fixtures before live ingestion is complete.

## Validation

- replay query returns persisted events only
- demo fixtures still work when live sources are unavailable
- provenance and event-time semantics are preserved on export and playback

## Gate review

- [ ] New event family contracts are frozen
- [ ] Supported feeds persist raw payloads and normalized events
- [ ] Replay works for 24h, 7d, and 30d windows
- [ ] Frontend playback uses the persisted query path
