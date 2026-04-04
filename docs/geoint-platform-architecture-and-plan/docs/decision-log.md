# Decision Log

## ADR-001 — Free/public and Middle East support are gating constraints
**Status:** Accepted  
**Decision:** Favor free/public and Middle East-capable sources first; only add commercial sources where public sources cannot meet validated user needs.  
**Why:** Limits cost and licensing exposure while fitting the pilot objective.  
**Consequence:** MVP will not promise premium imagery resolution or guaranteed global real-time coverage.

## ADR-002 — STAC-first imagery interoperability
**Status:** Accepted  
**Decision:** Use STAC as the primary imagery interoperability layer; start with CDSE and Earth Search.  
**Why:** It standardizes search/discovery across imagery catalogs and avoids provider lock-in.  
**References:** https://www.ogc.org/standards/stac/, https://documentation.dataspace.copernicus.eu/APIs/newSTACcatalogue.html, https://element84.com/earth-search/

## ADR-003 — Operational store is PostGIS, not a data lake
**Status:** Accepted  
**Decision:** Use PostgreSQL/PostGIS + object storage as the operational core; defer warehouse/lake complexity.  
**Why:** Smaller operational footprint, faster delivery, and enough capability for MVP/Phase 2.

## ADR-004 — 2D operational map first; 3D globe second
**Status:** Accepted  
**Decision:** MapLibre is the primary operational surface. globe.gl is for overview/storytelling.  
**Why:** Analysts need precision and inspectability more than spectacle.  
**References:** https://maplibre.org/maplibre-gl-js/docs/, https://globe.gl/

## ADR-005 — deck.gl owns dense overlay and playback rendering
**Status:** Accepted  
**Decision:** Use deck.gl overlays, especially TripsLayer, for temporal path trails and dense point/path rendering.  
**Why:** Performance and consistent playback semantics.  
**References:** https://deck.gl/docs/api-reference/geo-layers/trips-layer

## ADR-006 — Streaming is optional, not default
**Status:** Accepted  
**Decision:** Use polling/batch by default; add streaming only for bounded use cases where user value justifies complexity.  
**Why:** Most source families are not truly streaming and premature streaming infrastructure is an overengineering trap.

## ADR-007 — Canonical event model is narrow at the core and extensible in attributes
**Status:** Accepted  
**Decision:** Keep the top-level event schema compact and source-agnostic; use `attributes` for family-specific fields.  
**Why:** Prevents schema sprawl and connector lock-in.

## ADR-008 — DuckDB Spatial is the default local analytics tool
**Status:** Accepted  
**Decision:** Provide DuckDB Spatial extracts for offline analyst workflows and QA.  
**Why:** It is lightweight, reproducible, and avoids immediate warehouse complexity.  
**References:** https://duckdb.org/docs/stable/core_extensions/spatial/overview

## ADR-009 — Public OSM services are not assumed to be production-scale
**Status:** Accepted  
**Decision:** Use public OSM-derived services sparingly in MVP and prepare for self-hosting or commercial substitution later.  
**Why:** Public acceptable-use policies and rate limits make them unreliable at scale.

## ADR-010 — Construction-change analytics requires analyst review
**Status:** Accepted  
**Decision:** No fully automated production change verdicts in early phases.  
**Why:** Public imagery quality and contextual ambiguity make analyst-in-the-loop review essential.
