# Phase 2: Article-Parity Operational Layers

## Objective

Add the major missing operational layers described in the articles: satellite orbits/passes, airspace restrictions, GPS jamming, and strike/event reconstruction.

## Entry Criteria

- Phase 1 exit criteria met
- Unified data plane contracts are stable enough for new source families

## Exit Criteria

- New event families are represented in the shared model
- New layers exist in backend APIs, frontend types, map/globe rendering, and timeline synchronization
- Each layer can participate in historical replay

## Track A: Satellite Orbits And Passes

- `[x]` Add event models for `satellite_orbit` and `satellite_pass` — `src/models/operational_layers.py`
- `[x]` Add an orbit source connector or ingestion adapter — `src/connectors/orbit_connector.py` (TLE-based stub, deterministic)
- `[x]` Render orbits and passes on 2D and 3D views
- `[x]` Add orbit/pass visibility controls and legend entries
- `[x]` Add replay support for pass windows

## Track B: Airspace And No-Fly Restrictions

- `[x]` Add event models for `airspace_restriction` and `notam_event` — `src/models/operational_layers.py`
- `[x]` Add connector or ingestion adapter for relevant sources — `src/connectors/airspace_connector.py` (FAA-style stub)
- `[x]` Render airspace polygons and temporal restrictions
- `[x]` Add timeline sync and query filters — `active_only` filter on `/api/v1/airspace/restrictions`; ICAO filter on NOTAMs
- `[x]` Define how stale or expired restrictions are represented — `valid_to` + `is_active` + `AirspaceConnector.is_active()` UTC comparison

## Track C: GPS Jamming Layer

- `[x]` Define `gps_jamming_event` or equivalent derived model — `src/models/operational_layers.py`
- `[x]` Design the detection or ingestion logic — `src/connectors/jamming_connector.py` (deterministic synthetic events)
- `[x]` Add confidence and provenance semantics for derived jamming events — `confidence` field + `detection_method` enum + mandatory `provenance`
- `[x]` Render jamming heat or footprint layers
- `[x]` Add replay and filtering support

## Track D: Strike And Event Reconstruction

- `[x]` Define `strike_event` and associated evidence metadata — `src/models/operational_layers.py`; `EvidenceLink` cross-cutting model
- `[x]` Add ingestion paths for strike markers and reconstructed event points — `src/connectors/strike_connector.py` (ACLED-style stub)
- `[x]` Render strike markers and relevant context on map and globe
- `[x]` Add timeline correlation views
- `[x]` Add evidence linkage hooks for future investigation workflows — `POST /api/v1/strikes/{strike_id}/evidence`; idempotent by `evidence_id`

## Track E: Cross-Layer Synchronization

- `[x]` Update frontend types and query hooks for all new layer families — `frontend/src/types/operationalLayers.ts`, `frontend/src/api/operationalLayersApi.ts`, `frontend/src/hooks/useOperationalLayers.ts`
- `[x]` Add legend and layer panel controls — `frontend/src/components/LayerPanel/OperationalLayersPanel.tsx`
- `[x]` Ensure timeline controller synchronizes all new operational layers — `frontend/src/components/TimelinePanel/useTimelineSync.ts`
- `[x]` Add end-to-end tests for mixed-layer replay — `tests/integration/test_operational_layers_replay.py` (33 tests, 8 scenarios, all pass)

## Backend APIs Registered (2026-04-04)

- `GET /api/v1/orbits` — list orbits; `GET /api/v1/orbits/{id}` — single orbit; `GET /api/v1/orbits/{id}/passes` — pass predictions
- `GET /api/v1/airspace/restrictions` — list restrictions (`active_only` filter); `GET /api/v1/airspace/notams` — list NOTAMs (ICAO filter)
- `GET /api/v1/jamming/events` — jamming events; `GET /api/v1/jamming/heatmap` — weighted heat points
- `GET /api/v1/strikes` — strike events; `GET /api/v1/strikes/summary` — counts by type; `POST /api/v1/strikes/{id}/evidence` — evidence linking

## Suggested Subagent Split

- Subagent 1: Track A
- Subagent 2: Track B
- Subagent 3: Track C
- Subagent 4: Track D
- Main thread or Subagent 5: Track E after API stubs are ready

## Notes

- Each backend connector track can run in parallel after the schema freeze.
- Cross-layer UI work should start from stubbed contracts, not from final backend completion.
