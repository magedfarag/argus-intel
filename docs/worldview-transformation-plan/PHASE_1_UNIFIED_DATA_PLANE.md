# Phase 1: Unified Historical Data Plane

## Objective

Create one durable replayable data plane for imagery, telemetry, and contextual feeds.

## Entry Criteria

- Phase 0 exit criteria met

## Exit Criteria

- Live sources can be persisted, normalized, and queried historically
- `EventStore` and `TelemetryStore` responsibilities are reconciled or wrapped behind one query contract
- Playback works against the unified timeline for 24h, 7d, and 30d windows
- Provenance and raw payload retention are defined for each source family

## Track A: Schema And Contract Freeze

- `[x]` Define canonical event extensions needed for unified replay
- `[x]` Document what remains in canonical events versus specialized telemetry projections
- `[x]` Update frontend API types for any new shared query contracts
- `[x]` Freeze playback and timeline response contracts before broad implementation

## Track B: Ingestion And Persistence

- `[x]` Persist raw payload references for AIS, OpenSky, GDELT, and imagery
- `[x]` Persist normalized events with source, provenance, and license metadata
- `[x]` Define retention behavior for raw versus normalized data
- `[x]` Add replay-safe backfill and idempotent ingest semantics

## Track C: Query And Replay Unification

- `[x]` Design one historical query path for event and telemetry playback
- `[x]` Refactor `src/api/playback.py` to depend on the unified query path
- `[x]` Materialize or cache 24h, 7d, and 30d playback windows
- `[x]` Ensure timeline, map, and track hooks consume the same historical contract

## Track D: Verification

- `[x]` Add integration tests for persisted replay queries
- `[x]` Add regression tests for late-arrival handling
- `[-]` Add performance budgets for pilot AOI replay windows  <!-- deferred: Phase 6 scope — requires production data and load profiles -->
- `[x]` Validate that imagery, contextual, ship, and aircraft layers can all replay from the same time model

## Suggested Subagent Split

- Subagent 1: Track A
- Subagent 2: Track B
- Subagent 3: Track C
- Subagent 4: Track D after contracts are frozen

## Notes

- Track A and Track B can begin in parallel.
- Track C should start once Track A is stable enough to prevent contract churn.
