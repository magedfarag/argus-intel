# ARGUS Data Contracts — Phase 1 Freeze

## Status
These contracts are frozen as of Phase 1. Changes require updating this document and all derivative artifacts simultaneously.

## CanonicalEvent Schema Version
schema_version: "1.0" (from NormalizationRecord.schema_version)

## Entity ID Semantics
| entity_type | entity_id value |
|-------------|----------------|
| VESSEL | MMSI string (9 digits, zero-padded) |
| AIRCRAFT | ICAO24 hex string |
| IMAGERY_SCENE | Catalogue scene ID (e.g., Sentinel-2 SAFE path) |
| CONTEXTUAL_EVENT | GDELT event ID when available, else None |
| PERMIT | Permit number from authority |

## Late-Arrival Detection
An event is flagged as a late arrival when event_time < max(event_time seen from same source).
There is currently no grace period or tolerance window. This decision is frozen for Phase 1.
Revisit in Phase 6 hardening if operators need tolerance windows.

## EventStore Query Contract
Supported filters: time-range (required), aoi_id, event_types, source_types, sources, confidence_threshold, pagination
NOT supported: spatial viewport filter (routed to TelemetryStore for position events)
Freeze: EventSearchRequest must not diverge from EventStore.search() capabilities.

## TelemetryStore Query Contract
Only accepts: SHIP_POSITION and AIRCRAFT_POSITION event types
Entity query: entity_id (MMSI or ICAO24), time range, max_points
Viewport query: bbox [west, south, east, north], time range, sources, max_events
Freeze: TelemetryStore.ingest() interface must not change without updating all 6+ callers.

## Playback API Contract
Event playback: POST /api/v1/playback/query → PlaybackQueryRequest → PlaybackQueryResponse
Entity tracks: GET /api/v1/playback/entities/{entity_id} → EntityTrackResponse
Materialization: POST /api/v1/playback/materialize → async job with polling
Freeze: PlaybackQueryRequest shape must not change without versioning the endpoint.

## Store Responsibility Split (Phase 1 Interim)
- EventStore: all event types except high-frequency positional
- TelemetryStore: SHIP_POSITION + AIRCRAFT_POSITION only (high-frequency, needs thinning)
- Phase 1 defers unification to Phase 1 Track C (unified query contract)
- Phase 2 can fan out to new layer types only after this split is documented and stable

## Backend Persistence Status (Phase 1)
PostgreSQL schema is defined in src/storage/models.py + Alembic migrations.
Currently using in-memory stores (EventStore dict + TelemetryStore dict).
Activation requires DATABASE_URL env var + alembic upgrade head.
Cross-process sharing (FastAPI app ↔ Celery workers) requires PostgreSQL to be active.
