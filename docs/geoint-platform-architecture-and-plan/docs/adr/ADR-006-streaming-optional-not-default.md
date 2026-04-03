# ADR-006 — Streaming is optional, not default

## Status
Accepted

## Context
Several source families appear to offer real-time streaming (AIS via WebSocket, OpenSky near-real-time, GDELT near-real-time updates). Streaming infrastructure (WebSocket relay, SSE fan-out, Kafka topics) offers low latency but comes with high operational complexity: connection lifecycle management, fan-out fan-in guarantees, replay, and backpressure.

For the MVP the primary use case is AOI-bounded analysis over hours-to-days windows rather than sub-second situational awareness. Most sources' value lies in historical and windowed replay, not live alerts.

## Decision
1. **Default ingestion pattern: polling and batch.** All connectors implement a `fetch()` method callable on a schedule.
2. **Streaming is a bounded exception.** AISStream WebSocket is implemented because the source provides no polling API; it is bounded by `collect_timeout_s` and `max_messages` to prevent unbounded resource use.
3. **No streaming infrastructure by default.** No Kafka, Kinesis, Redis Streams, or SSE fan-out in the initial architecture.
4. WebSocket relay is backend-only; browsers never connect directly to source streams.

## Consequences
- `BaseConnector.fetch()` is synchronous and Celery-schedulable for all connectors.
- `AisStreamConnector` uses `asyncio` + `websockets` internally but exposes the same `fetch()` interface.
- `PlaybackService.enqueue_materialize()` runs synchronously in-memory, with a Celery-ready interface preserved for future upgrade.
- Ingest lag (median/p95) is monitored via `TelemetryStore.get_ingest_lag_stats()` and exposed on `/metrics`.
- Future streaming upgrade path requires only replacing `fetch()` internals, not the connector contract.

## Implementation notes
- `src/connectors/ais_stream.py` — WebSocket with bounded collection
- `src/connectors/opensky.py` — polling REST API
- `src/connectors/gdelt.py` — polling REST/bulk API, 15-min Celery beat
- `app/workers/celery_app.py` — beat schedules for all polling connectors
