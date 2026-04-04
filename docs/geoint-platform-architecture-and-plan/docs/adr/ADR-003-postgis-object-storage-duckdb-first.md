# ADR-003 — PostGIS + object storage + DuckDB before any warehouse

## Status
Accepted

## Context
The platform needs spatial search, temporal filtering, replay, and offline analysis, but not yet enterprise-scale historical warehousing.

## Decision
Use PostgreSQL/PostGIS as the operational canonical store, object storage for raw payloads/artifacts, and DuckDB Spatial for offline analysis. Defer warehouse/lakehouse decisions.

## Consequences
- Lower operational complexity.
- Faster MVP delivery.
- Future migration path still exists if scale demands it.
