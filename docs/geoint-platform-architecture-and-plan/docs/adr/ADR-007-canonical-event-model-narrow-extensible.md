# ADR-007 — Canonical event model is narrow at the core and extensible in attributes

## Status
Accepted

## Context
The platform ingests events from five distinct source families: imagery, telemetry (ships, aircraft), administrative records (permits, complaints), and contextual events (news, GDELT). These families have fundamentally different schemas — a STAC imagery item shares almost no fields with an AIS position message.

Two extremes were considered:
1. **Fully normalized**: A single wide table/model with all possible fields from every source family. Results in schema sprawl, nullable fields everywhere, and connector lock-in.
2. **Fully polymorphic**: Each family has its own separate model. Results in fragmented search, cross-source timeline replay requires union logic, and each API would need family-specific endpoints.

## Decision
Adopt a **narrow core + extensible attributes** design:
- A compact top-level `CanonicalEvent` model with fields common to ALL events: `event_id`, `event_time`, `source`, `source_type`, `entity_type`, `event_type`, `geometry`, `centroid`, `confidence`, `normalization`, `provenance`, `license`, `correlation_keys`.
- Family-specific attributes are placed in a typed `attributes` dict/model, optional per event.

Schema changes to the core require an ADR. Schema changes to `attributes` models are lower-ceremony.

## Consequences
- `src/models/canonical_event.py` — single `CanonicalEvent` Pydantic v2 model; sub-models for `NormalizationRecord`, `ProvenanceRecord`, `LicenseRecord`, `CorrelationKeys`.
- Timeline search, replay, and export all operate on the canonical core fields without family-specific dispatch.
- Family-specific attributes (`ImageryAttributes`, `ShipPositionAttributes`, `AircraftAttributes`, etc.) are typed but optional.
- `make_event_id()` generates deterministic SHA-256-based IDs from `(source, entity_id, event_time)` enabling safe upserts.
- The `canonical-event.schema.json` in `schemas/` is the normative source for the core model.

## Implementation notes
- `src/models/canonical_event.py` — Pydantic v2 model; all fields typed; UTC enforcement via validator
- `schemas/canonical-event.schema.json` — JSON Schema (canonical source)
- `tests/unit/test_canonical_event.py` — ≥32 validation tests
