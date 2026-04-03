# ADR-009 — Public OSM services are not assumed to be production-scale

## Status
Accepted

## Context
OpenStreetMap-derived services (Nominatim geocoding, Overpass API, openrouteservice) are used in the MVP for geocoding AOI addresses, reverse-geocoding entity positions, and routing context. All three are available as free public instances.

However:
- Nominatim's public instance enforces a 1 req/s rate limit and prohibits bulk geocoding.
- Overpass API public instances are subject to fair-use throttling and occasional downtime.
- These services are ODbL-licensed; redistribution of derived data must preserve the license.

## Decision
1. **Use public OSM services sparingly** in MVP: geocoding only on user-triggered events, not in bulk background jobs.
2. **Do not cache OSM results beyond session scope** without legal review of redistribution obligations.
3. **Self-hosting plan is documented** but not activated until MVP validates the need: an internal Nominatim + Overpass instance can be added to `docker-compose.yml` when usage metrics warrant it.
4. **Commercial geocoder substitution** (e.g., Mapbox, Google, HERE) is an upgrade path, not a default.

## Consequences
- No OSM-backed API routes exist in the current MVP that would trigger bulk background geocoding.
- `docs/RUNBOOK.md` documents the self-hosting upgrade path for Nominatim and Overpass.
- If a commercial geocoder is added, it must go behind the same `BaseConnector` abstraction and be gated on a config flag, not hardcoded.
- Risk R-011 monitors this constraint.

## Implementation notes
- No OSM connector currently in `src/connectors/` (deferred per this ADR)
- `docs/RUNBOOK.md` — self-hosting upgrade path documented
- `docs/geoint-platform-architecture-and-plan/data/source_inventory_classified.csv` — OSM services classified as `Truly free/public` with rate-limit caveats
