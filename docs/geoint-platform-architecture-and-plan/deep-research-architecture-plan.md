# Architecture and Delivery Plan for a Multi-Source Geospatial Intelligence Platform

## Packaged deliverables

A ready-to-use documentation bundle is attached as a ZIP: [geoint-platform-architecture-and-plan.zip](sandbox:/mnt/data/geoint-platform-architecture-and-plan.zip)

This bundle was produced by first inspecting the working directory and the uploaded Excel inventory (`tracking_sources_inventory_middle_east.xlsx`), extracting and classifying the 48 candidate sources, and then writing architecture and planning artifacts before adding any implementation scaffolding.

### Files created

- `README.md` (project direction and repo layout)
- `docs/architecture.md`
- `docs/delivery-plan.md`
- `docs/source-strategy.md`
- `docs/canonical-event-model.md`
- `docs/release-phases.md`
- `docs/risk-register.md`
- `docs/decision-log.md`
- `docs/adr/0001-canonical-event-model.md`
- `docs/adr/0002-storage-postgres-postgis.md`
- `docs/adr/0003-frontend-visualization-stack.md`
- `docs/adr/0004-aoi-first-design.md`
- `docs/adr/0005-source-strategy-free-first.md`
- `docs/adr/0006-defer-heavy-streaming.md`
- `docs/source-inventory-classified.csv`
- `docs/source-inventory-classified.json`
- `schemas/canonical_event.schema.json`
- `schemas/aoi.schema.json`
- `config/.env.example`

## Architecture summary

### Fact  
The target visualization architecture is explicitly aligned to:
- globe.gl as the 3D “overview / wow” layer (ThreeJS/WebGL-based). citeturn0search0  
- MapLibre GL JS as the 2D operational map and basemap renderer (WebGL vector-tile rendering). citeturn0search1turn0search9  
- deck.gl overlays for density and time playback, including TripsLayer for animated trails and replay semantics. citeturn0search2turn0search10  

### Interpretation  
To avoid overengineering while still supporting production releases per phase, the architecture uses an **AOI-first, replay-first** contract:
- AOI-first prevents “global real-time everything” from becoming a performance and cost trap.
- Replay-first forces correct time modeling, data retention, and deterministic playback early, before adding heavy analytics.

The system is designed as a modular core with connectors and workers, rather than a large microservices mesh. A large streaming backbone (Kafka/Flink) is explicitly deferred until measured throughput demands it. citeturn0search18  

### Recommendation  
Adopt the MVP/near-term storage and serving topology captured in `docs/architecture.md`:
- Primary store: PostgreSQL + PostGIS (event store + separate track store tables)
- Object storage: raw payloads and large artifacts (imagery quicklooks, derived analytics)
- Local/offline analytics: DuckDB Spatial on parquet exports for reproducible analysis and “analyst laptop” workflows citeturn1search1  
- Imagery interoperability: STAC-based discovery and caching strategy citeturn0search3turn0search7  
- Context feed: GDELT ingestion as near-real-time contextual signal (15-minute update cadence stated by GDELT). citeturn1search0turn1search4  

## Source strategy summary from the attached inventory

### Fact  
The attached Excel inventory contains 48 candidate sources across:
- Satellite/Public, Satellite/Commercial
- Maritime Tracking
- Aviation Tracking
- Construction/Admin
- Geo Tracking

The classification artifact is exported in `docs/source-inventory-classified.csv` and `docs/source-inventory-classified.json`, and summarized in `docs/source-strategy.md`.

### Interpretation  
The inventory contains a structurally important constraint: many “free” mobility feeds—especially aviation—carry **non-commercial** or restrictive terms. OpenSky’s official documentation explicitly positions its live API for research and non-commercial purposes and links to its terms of use. citeturn1search7turn1search3  
That makes a “free-only production aviation layer” a high-risk bet without a paid provider fallback.

Construction/public-record sources present the opposite risk: they may be legally usable, but **Middle East availability is uncertain and fragmented** by jurisdiction. This risk is handled in the plan by making imagery-driven monitoring the primary early construction signal, with public-record ingestion treated as a jurisdiction-by-jurisdiction connector expansion.

### Recommendation  
Follow the phased shortlist already encoded in the source strategy:

- **Phase 1 (free/public + Middle East-capable foundations):**
  - OSM-based geocoding/query via Nominatim/Overpass plus routing via openrouteservice (with an explicit plan to self-host before scale).
  - NASA GIBS as a fast global imagery/basemap overlay option.

- **Phase 2 (imagery + context, still free/public-first):**
  - STAC imagery sources and indexes, treated as catalog families, not one-off integrations. citeturn0search3turn0search11  
  - GDELT as the first “context layer” to support correlation and narrative timelines. citeturn1search0turn1search4  

- **Phase 3 (moving-object telemetry):**
  - Ships: integrate a real-time AIS stream and build playback via TripsLayer. citeturn0search2  
  - Aircraft: start with a constrained demo path (coverage validation + legal review), then switch to paid providers when commercial deployment requires it, because “free” aviation terms are frequently restrictive. citeturn1search7turn1search3  

- **Premium/future:** commercial SAR and high-revisit imagery, and commercial maritime/aviation feeds, behind provider abstractions.

## Canonical event model and normalization contract

### Fact  
A single canonical event envelope is specified in `docs/canonical-event-model.md` and formalized as JSON Schema in `schemas/canonical_event.schema.json`. It includes the required fields you mandated:
- IDs, source metadata, entity typing
- timestamp and time range
- geometry + centroid (+ optional bbox)
- confidence and attributes payload
- normalization metadata and provenance/raw reference
- ingestion time
- correlation keys
- license/access metadata

### Interpretation  
The canonical event envelope is the primary interoperability mechanism. It is the only way to keep a multi-source platform coherent when:
- sources arrive at different cadences (seconds vs daily vs irregular)
- spatial precision varies widely
- licensing/redistribution rules diverge

It also enables “replay” to be a platform-level feature rather than a per-source special case.

Time alignment and replay are built around STAC’s explicit spatiotemporal search semantics (date/time filtering, item collections) and the STAC API search model. citeturn0search3  

### Recommendation  
Keep two strict implementation rules (both documented in the canonical model and architecture docs):
- Store UTC internally for all observed and ingested times; never store local time.
- Persist **observed time** and **ingested time** separately and use per-source watermarks to handle late arrivals deterministically.

## Phased delivery plan summary

### Fact  
The plan in `docs/delivery-plan.md` defines six production-releasable phases aligned to your required roadmap philosophy. The phases explicitly prioritize free/public sources first and Middle East AOI suitability, and defer heavyweight infrastructure until proven necessary.

### Interpretation  
The sequencing intentionally avoids a common failure mode: implementing expensive ingestion infrastructure before delivering any user-visible workflow. Instead, each phase is a thin vertical slice that reaches production:
- Phase 1 proves AOI workflows and canonical query semantics.
- Phase 2 proves imagery discovery and context correlation.
- Phase 3 proves dense moving-object playback with TripsLayer.
- Phase 4 delivers the first real construction monitoring workflow (change candidates + analyst review).
- Phase 5 hardens scaling, governance, and compliance.

TripsLayer is chosen explicitly for playback because it is designed around trails and fade-out controls (trail length, timestamps-driven paths), which matches the “movement over time” UI requirement. citeturn0search2  

### Recommendation  
Hold a formal gate review at the end of each phase using the “release criteria” and “operational readiness criteria” fields already written into the delivery plan, and do not allow Phase 3 telemetry volume to dictate backend architecture until Phase 1–2 prove the query, caching, and replay contracts.

## Key decisions, risks, and intentional deferrals

### Fact  
The decision log and ADRs explicitly lock these choices:
- Canonical event envelope with provenance + licensing metadata
- PostgreSQL + PostGIS as initial primary store; separate track store
- Required frontend stack: globe.gl + MapLibre GL JS + deck.gl (TripsLayer)
- AOI-first product design
- Free/public-first with provider abstraction
- Defer Kafka and heavy stream processing until required by measured throughput

### Interpretation  
The strongest counterarguments and likely failure modes are:
- “Free” aviation data is not production-legal for many commercial deployments. citeturn1search7turn1search3  
- Public endpoints (geocoding/query) can block you at scale; self-hosting is a near-certainty once usage grows.
- Dense moving-object layers can overwhelm browsers; TripsLayer requires sampling, track segmentation, and AOI gating to stay performant. citeturn0search2  
- Construction public records in the Middle East may not exist in usable open form; imagery-driven change must carry the initial monitoring value.

### Recommendation  
The single best next implementation step after architecture approval is:

**Implement Phase 1 as written: AOI + canonical event store + event search + timeline aggregation + MapLibre UI with AOI selection.**  
Do not implement maritime/aviation ingestion until Phase 2’s time alignment and replay semantics are stable and measurable against real AOIs.

