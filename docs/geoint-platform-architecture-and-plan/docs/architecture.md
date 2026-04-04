# Architecture — Multi-Source Geospatial Intelligence Platform

## 1. Executive summary

This platform is a phased geospatial intelligence system for construction activity monitoring, satellite and aerial imagery analysis, maritime tracking, air traffic tracking, and broader contextual geospatial/event monitoring in and around areas of interest (AOIs). It is designed for analysts, client stakeholders, engineering teams, and product leadership.

The architecture is intentionally phased. The source landscape is heterogeneous: the inventory contains 48 candidate sources, only 18 of which are marked truly free/public, while Middle East suitability varies and many operational feeds carry licensing or coverage caveats. The source inventory also explicitly warns that community-fed AIS, ADS-B, OSM, and street-level sources can be uneven by country, and that Middle East coverage flags are screening indicators rather than legal guarantees. This makes a "build everything first" approach high-risk and wasteful.

Free-first and Middle East support are primary design constraints because they directly affect feasibility, cost, commercial-use risk, and client value. The recommended near-term stack is therefore: STAC-based public imagery discovery, GDELT for context, selected public AOI records where available, AIS and ADS-B sources with explicit caveats, DuckDB Spatial for local exploration, and a thin production API + map client that can expand later without a rewrite.

## 2. Problem framing

### Source classes

1. **Imagery sources**
   - Public EO catalogs and imagery archives: Copernicus Data Space Ecosystem, Earth Search, Microsoft Planetary Computer, NASA HLS, NASA GIBS, Landsat.
   - Commercial escalation paths: Sentinel Hub, Planet, Maxar, ICEYE, UP42.
   - Problem: revisit cadence, cloud/SAR trade-offs, catalog interoperability, and cost asymmetry.

2. **Vessel tracking sources**
   - AISStream, AISHub, Global Fishing Watch, MarineTraffic, VesselFinder, Spire Maritime.
   - Problem: different transport mechanisms (WebSocket vs REST), varying historical availability, uneven receiver density, and commercial-use restrictions.

3. **Aviation tracking sources**
   - OpenSky, ADS-B Exchange, FlightAware, Flightradar24, Spire Aviation.
   - Problem: non-commercial restrictions on some "free" feeds, freshness differences, and divergent licensing on redistribution.

4. **Administrative/public-record sources**
   - Municipal open-data portals, ArcGIS Feature Services, BLDS, Open311, Accela, OpenGov, Tyler.
   - Problem: local authority dependence, fragmented schemas, and uncertain Middle East availability.

5. **Contextual event/news sources**
   - GDELT first; later optional paid enrichment if needed.
   - Problem: wide coverage but uneven signal quality, language/media bias, and non-authoritative nature.

6. **Mapping/geocoding/basemap services**
   - OpenStreetMap-derived services first (Nominatim, Overpass, openrouteservice), then optional commercial geocoders.
   - Problem: public service rate limits and ODbL/acceptable-use obligations.

### Why the problem is hard

Each source family differs in:
- **update cadence** — from sub-second streaming to irregular contributed imagery;
- **spatial fidelity** — from 10 m optical raster to point tracks with meter-level GPS;
- **licensing** — from open standards to quote-based enterprise contracts;
- **interfaces** — STAC, OData, WMTS, REST, WebSocket, bulk file drops, tiles;
- **trust** — official records, community networks, model-derived events, or media-derived context.

The platform therefore cannot treat all feeds as equivalent. It needs source-specific ingestion, explicit provenance, and a canonical event model that preserves uncertainty.

## 3. Target use cases

### MVP use cases
- Select an AOI and view all available operational layers on a 2D map.
- Discover Sentinel/Landsat imagery intersecting the AOI using STAC.
- View contextual GDELT events in and around the AOI over time.
- Run timeline queries by AOI, source, entity type, and date range.
- Replay normalized events for the AOI over a selected time window.
- View maritime and aviation activity only for sources explicitly enabled for the pilot.

### Phase 2 use cases
- Compare imagery acquisitions and external events on a synchronized timeline.
- Blend public records, complaints, and contextual events with imagery search.
- Replay ship and aircraft tracks with path trails and filtering.
- Export map, timeline, and source health snapshots for analysts and stakeholders.

### Future / premium use cases
- Commercial sub-meter imagery ordering and premium SAR.
- Automated construction-change scoring with analyst review.
- Entity-centric watchlists, alerts, and customer-specific rules.
- High-volume enterprise APIs and multi-tenant deployments.

## 4. System context and major components

1. **Frontend visualization layer**
   - React/TypeScript shell
   - MapLibre GL JS for 2D operations
   - globe.gl for 3D overview / storytelling
   - deck.gl overlays for dense point/path rendering and TripsLayer playback

2. **API gateway / backend**
   - REST + limited streaming endpoints
   - AOI, timeline, playback, imagery search, source health, analytics jobs, export

3. **Ingestion services**
   - Connector-specific workers
   - Batch fetchers for STAC, GDELT, records, and historical data
   - Streaming relays for AIS/ADS-B where appropriate

4. **Normalization pipeline**
   - Raw source capture
   - source-specific parsing
   - canonical event transformation
   - validation, deduplication, provenance tagging, confidence assignment

5. **Temporal-spatial storage layer**
   - PostgreSQL + PostGIS for canonical operational store
   - object storage for raw payloads/artifacts
   - optional Redis cache for hot query windows
   - DuckDB Spatial for offline analytics and reproducible analyst notebooks

6. **Imagery catalog/search layer**
   - STAC-first search abstraction
   - catalog adapters for CDSE, Earth Search, MPC, and later commercial providers

7. **Event correlation layer**
   - AOI/time-window joins
   - spatial proximity linking
   - entity linking via vessel IDs, flight identifiers, permit IDs, and synthetic keys

8. **Job orchestration / workers**
   - scheduled polling
   - async replay materialization
   - export/report generation
   - heavier change-analysis tasks

9. **Analytics layer**
   - temporal correlation
   - basic scoring and heuristics
   - analyst-oriented derived tables

10. **Export/reporting layer**
    - CSV/GeoJSON exports
    - evidence packs
    - timeline/map snapshots

11. **Observability/security/configuration layer**
    - structured logs, metrics, health checks, secrets, license flags, provider throttling

## 5. Logical architecture

### End-to-end flow

```text
Source -> connector/adapter -> raw landing -> parse/normalize -> canonical event store -> query APIs -> map/timeline/playback UI
                                           \-> object storage -------------------/
                                           \-> analytics extracts / DuckDB -----/
```

### Ingestion modes

- **Streaming**: AISStream and future streaming relays.
- **Near-real-time polling**: OpenSky, GDELT, some municipal services.
- **Batch/historical pulls**: STAC searches, Landsat/HLS inventories, historical reports, selected vessel/flight history providers.
- **Manual/partner upload**: permit datasets, inspection exports, or private client layers.

### Transformation and normalization

Every connector emits:
- raw payload;
- normalized event(s);
- source metadata;
- normalization warnings/errors.

The normalization service must preserve:
- original timestamps;
- original identifiers;
- raw geometry or bbox where available;
- access/license metadata;
- confidence and quality notes.

### Storage

- **PostGIS**: canonical events, AOIs, tracks, derived summaries, source metadata.
- **Object storage**: raw payloads, imagery metadata dumps, exports, screenshots, cached footprints.
- **DuckDB Spatial**: local/repro analytics, QA, pilot-grade ad hoc analysis.
- **Redis (optional after phase 2)**: hot playback windows and source-health snapshots.

### Query and map rendering APIs

- REST for search, metadata, AOIs, exports, source health.
- Server-side tile/vector simplification for dense layers when needed.
- Streaming or SSE/WebSocket only where client-visible latency justifies complexity.

### Caching and extensibility

Do not cache everything. Cache:
- STAC search results by AOI/time/filter for short TTLs;
- playback segments for recently viewed windows;
- source health snapshots;
- basemap style metadata.

Do not precompute global track playback for all feeds in MVP.

## 6. Canonical event model

See `docs/canonical-event-model.md` and `schemas/canonical-event.schema.json` for the normative form.

The canonical event model must represent:
- imagery acquisitions;
- detected changes;
- ship positions and reconstructed tracks;
- aircraft positions and reconstructed tracks;
- permits / inspections / complaints / project records;
- GDELT/contextual events.

### Core fields

- `event_id`
- `source`
- `source_type`
- `entity_type`
- `event_type`
- `event_time`
- `time_start`
- `time_end`
- `geometry`
- `centroid`
- `altitude_m` / `depth_m` when relevant
- `confidence`
- `attributes`
- `normalization`
- `provenance`
- `ingested_at`
- `correlation_keys`
- `license`
- `quality_flags`

### Time alignment strategy

- Standardize all internal timestamps to UTC.
- Preserve source-local timestamp strings if provided.
- Store both event-time and ingest-time.
- For tracks, store observed fixes and optionally materialized playback segments.
- Use event-time for analytics; ingest-time for monitoring and freshness.

### Late-arriving data

- Accept late data as first-class.
- Upsert by deterministic `event_id` + `source` + `source_record_version`.
- Maintain `first_seen_at` and `last_seen_at`.
- Re-run affected correlation windows only for impacted AOI/time partitions.

### Deduplication

- Source-native deterministic IDs first.
- Fallback fuzzy matching by `(source, entity_id, time bucket, geometry proximity, event_type)`.
- Keep one canonical record and attach duplicates as provenance links.

### Source confidence ranking

Recommended default order:
1. official government/authority records;
2. official EO mission metadata;
3. direct telemetry networks with transparent caveats;
4. curated aggregators;
5. model-derived or media-derived contextual events.

### Entity linking / correlation approach

- **Vessels**: MMSI, IMO, callsign, provider-specific vessel IDs.
- **Aircraft**: icao24, callsign, tail/registration where available.
- **Records**: permit/project/inspection IDs, parcel IDs, authority IDs.
- **Imagery**: scene IDs, STAC item IDs, collection IDs.
- **Context**: AOI/time overlap + resolved place/organization/entity keys.
- Use soft links first. Hard-link only when identifiers are strong.

## 7. Source interoperability strategy

### STAC-compatible imagery catalogs
- **Ingestion mode**: batch search and metadata retrieval.
- **Cadence**: daily to mission-dependent.
- **Normalization path**: STAC Item -> imagery acquisition event.
- **Storage**: canonical event row + raw STAC JSON in object storage.
- **MVI**: CDSE + Earth Search first.
- **Limitations**: raster analytics and commercial ordering remain external in early phases.

### GDELT event/news
- **Ingestion mode**: polling/batch over AOI/time/topic filters.
- **Cadence**: near-real-time.
- **Normalization path**: document/event hit -> contextual event.
- **Storage**: canonical event + raw response excerpt/URI.
- **MVI**: AOI/time-window context only, no heavy NLP pipeline in MVP.
- **Limitations**: not authoritative and can be noisy.

### Vessel / AIS feeds
- **Ingestion mode**: backend WebSocket relay or bounded polling depending on provider.
- **Cadence**: real-time to near-real-time.
- **Normalization path**: position report -> ship_position event; optional segment builder -> ship_track events.
- **Storage**: point events in PostGIS; optional aggregated track segments.
- **MVI**: AISStream first; AISHub/GFW second.
- **Limitations**: public coverage uneven; browser-direct access is unsuitable for AISStream.

### Aviation / ADS-B feeds
- **Ingestion mode**: polling or provider API fetches.
- **Cadence**: near-real-time.
- **Normalization path**: state vector -> aircraft_position event; optional track reconstruction.
- **Storage**: point events + track segments.
- **MVI**: OpenSky first, ADS-B Exchange later.
- **Limitations**: free tiers often restrict commercial use.

### Public records / permits / inspections
- **Ingestion mode**: API polling, dataset snapshots, or manual source onboarding.
- **Cadence**: dataset-specific.
- **Normalization path**: record -> permit/inspection/project event.
- **Storage**: canonical events + reference tables.
- **MVI**: where a target authority exposes public records or GIS layers.
- **Limitations**: Middle East coverage is authority-specific.

### Basemap / geocoding services
- **Ingestion mode**: live query, cached result, or self-hosted instances later.
- **Cadence**: on demand.
- **Normalization path**: not canonicalized as events unless explicitly stored as geocoding results.
- **Storage**: cached responses only where allowed.
- **MVI**: OSM-derived services first.
- **Limitations**: public endpoints are not production scale.

## 8. Data storage and query design

### Recommended practical storage strategy

#### PostgreSQL + PostGIS (system of record)
Persist:
- AOIs and saved views
- canonical events
- entity registry tables
- source catalog metadata
- track segment summaries
- analyst annotations
- export job metadata

Why:
- transactional;
- strong geospatial indexing;
- simple operational footprint;
- mature tooling.

#### Object storage
Persist:
- raw source payloads
- STAC JSON and metadata dumps
- large export artifacts
- optional imagery quicklooks / thumbnails
- ingest audit evidence

Why:
- cheap retention;
- immutable evidence;
- avoids bloating relational tables.

#### DuckDB Spatial
Persist locally or in controlled analyst environments:
- curated extracts
- replay experiments
- QA / validation runs
- notebook-friendly analysis

Why:
- low-cost local analytics;
- excellent for offline and reproducible exploration;
- reduces pressure on the operational database.

#### Cache layer (phase 3+)
Cache only:
- hot timeline windows
- frequent AOI searches
- source health/status
- pre-simplified playback tiles

#### Optional future warehouse
Only after usage proves need:
- columnar history store for large-scale global analytics;
- e.g. Parquet + Iceberg/Lakehouse or managed warehouse.

### Historical replay

Replay is driven from canonical events, not directly from raw source payloads. The playback service:
1. queries events by AOI/time/source/entity filters;
2. groups by entity;
3. orders by event time;
4. interpolates only where the source semantics allow it;
5. returns playback-friendly frames or track segments.

### Time-window queries

All operational queries accept:
- AOI geometry or AOI ID
- start/end UTC
- source filters
- entity/event type filters
- quality/confidence thresholds

Use composite indexes on `(event_time, source, entity_type)` plus PostGIS geometry indexes.

## 9. Frontend architecture

### Why two map modes

- **globe.gl** is the 3D "wow" and portfolio/storytelling layer. It is valuable for executive overviews, regional movement context, and cinematic playback.
- **MapLibre GL JS** is the primary operational surface. Analysts need precise AOI selection, layer control, filtering, and inspectable 2D interactions.
- **deck.gl** provides the dense overlay engine on both, especially for moving-object layers and TripsLayer playback.

### User mode split

- **Globe view**: regional context, high-level movement arcs, portfolio/demo mode, large geographic extents.
- **Flat map view**: operational workflows, AOI editing, measurements, precise layer inspection, timeline-driven analysis.

### Temporal playback

Playback is controlled by a unified timeline component:
- global playhead in UTC
- source toggles
- trail length
- playback speed
- window presets (24h, 7d, 30d, custom)

Use deck.gl `TripsLayer` for path trails. For dense live points, degrade gracefully to clustered/simplified layers and disable expensive labels at low zoom.

### Layer groups

1. Basemap / AOI
2. Imagery footprints and acquisitions
3. Construction/admin records
4. Context/news events
5. Maritime tracks
6. Aviation tracks
7. Derived analytics / alerts
8. Annotations and exports

### AOI selection

Support:
- point + radius
- bbox
- polygon
- imported GeoJSON

AOI is a first-class object used across search, replay, export, and alerts.

### Performance strategy

- default to bounded AOIs, not global unconstrained queries;
- cap live moving-object layers by viewport, zoom, and time window;
- use server-side aggregation or vector tiles when counts exceed thresholds;
- separate hover/detail interactions from base rendering;
- keep the 3D globe presentation-oriented, not the sole operational canvas.

## 10. API architecture

Illustrative API surfaces:

### AOIs
- `POST /api/v1/aois`
- `GET /api/v1/aois/:id`
- `GET /api/v1/aois`
- `DELETE /api/v1/aois/:id`

### Imagery
- `POST /api/v1/imagery/search`
- `GET /api/v1/imagery/items/:id`
- `POST /api/v1/imagery/compare`
- `GET /api/v1/imagery/providers`

### Events
- `POST /api/v1/events/search`
- `GET /api/v1/events/:event_id`
- `GET /api/v1/events/timeline`
- `GET /api/v1/events/sources`

### Playback / tracks
- `POST /api/v1/playback/query`
- `GET /api/v1/playback/entities/:entity_id`
- `POST /api/v1/playback/materialize`
- `GET /api/v1/playback/jobs/:job_id`

### Source health / configuration
- `GET /api/v1/sources`
- `GET /api/v1/sources/:source/health`
- `GET /api/v1/sources/:source/license`
- `POST /api/v1/admin/reingest`

### Analytics / exports
- `POST /api/v1/analytics/change-detection`
- `POST /api/v1/analytics/correlation`
- `POST /api/v1/exports`
- `GET /api/v1/exports/:job_id`

## 11. Security and compliance

- Use environment-based secrets or a secret manager from phase 1.
- Never expose provider credentials to the browser.
- Separate public-source credentials from premium partner credentials.
- Enforce provider-aware throttling and retry policies.
- Persist source license flags with every connector and event family.
- Keep raw payload retention configurable per provider.
- Log who ran exports and which restricted sources they included.
- Tag sources as:
  - public/open;
  - public with acceptable-use restrictions;
  - non-commercial only;
  - commercial subscription;
  - redistribution restricted.

## 12. Observability and operability

Minimum requirements from phase 0:
- structured logs with source, connector, AOI/job IDs;
- `/healthz` and `/readyz` endpoints;
- metrics for ingest counts, ingest lag, error rate, freshness, cache hit rate, export latency;
- source freshness dashboard;
- source failure visibility by connector;
- cost/usage metrics for any paid provider.

Important operational metrics:
- last successful poll per source
- median/95th percentile ingest delay
- playback query duration
- number of late-arriving events
- duplicate suppression count
- STAC search success rate
- streaming connection resets per hour

## 13. Key trade-offs

### Free vs paid
Recommendation: maximize free/public value first, but design explicit upgrade seams for commercial imagery and data.

### Global vs Middle East-ready
Recommendation: optimize for Middle East pilot relevance before claiming global operational maturity.

### Real-time vs historical
Recommendation: early product value comes from "fresh enough + replayable", not from pretending every source is truly real-time.

### Optical vs SAR
Recommendation: use both. Optical is easier to interpret. SAR is essential where clouds or night conditions matter.

### 2D vs 3D
Recommendation: 2D is the operational default. 3D is additive, not primary.

### Batch vs streaming
Recommendation: batch/polling for most feeds; streaming only where it materially improves the user experience.

### Simplicity vs extensibility
Recommendation: single operational database + object storage + DuckDB first; avoid warehouse/lake complexity until justified.

## 14. Strongest counterarguments, hidden assumptions, and failure modes

### Strongest counterarguments
- Public sources may be too sparse or too delayed for meaningful construction monitoring.
- Middle East authority data may be unavailable or non-standardized.
- Community-fed AIS/ADS-B may underperform in specific markets.
- The requested multi-domain scope may tempt the team into building a generic platform before proving a narrow workflow.

### Hidden assumptions
- Relevant target authorities publish enough data to be useful.
- Users accept "public-source truth with caveats" rather than perfect operational intelligence.
- AOIs are bounded enough for public-source query economics and UI performance.
- Client expectations are managed around free-source resolution and latency limits.

### Likely failure modes
- licensing mistakes caused by mixing public and restricted data in exports;
- overloading the browser with dense moving-object feeds;
- false confidence from interpolated playback on sparse tracks;
- uncontrolled growth of source-specific special cases in the canonical model;
- early overinvestment in analytics before ingestion quality is stable.

## 15. Recommended architecture choice

### MVP architecture
- React + MapLibre GL JS + deck.gl
- globe.gl only for overview/story mode
- FastAPI or Node backend with source adapters
- PostgreSQL/PostGIS + object storage
- DuckDB Spatial for analyst/offline work
- STAC-first imagery discovery (CDSE + Earth Search)
- GDELT context
- selected free/public AOI records
- AISStream and OpenSky as bounded pilot feeds where legally and operationally appropriate

### Near-term production architecture
- Add replay materialization jobs
- Add Redis cache
- Add source-health dashboards and export controls
- Introduce AISHub/GFW/ADS-B Exchange as optional secondary feeds
- Add analyst annotation workflow
- Add imagery compare and first correlation scoring

### Later enterprise-scale evolution
- Commercial imagery and tasking adapters
- managed streaming infrastructure if truly required
- analytical warehouse/lake for large historical retention
- multi-tenant controls
- per-client source entitlements
- alerting and watchlists

## References

- OGC STAC: https://www.ogc.org/standards/stac/
- NASA Earthdata STAC overview: https://www.earthdata.nasa.gov/esdis/esco/standards-and-practices/stac
- Copernicus Data Space APIs: https://documentation.dataspace.copernicus.eu/APIs.html
- Copernicus STAC catalogue: https://documentation.dataspace.copernicus.eu/APIs/newSTACcatalogue.html
- Earth Search: https://element84.com/earth-search/
- DuckDB Spatial: https://duckdb.org/docs/stable/core_extensions/spatial/overview
- MapLibre GL JS: https://maplibre.org/maplibre-gl-js/docs/
- deck.gl TripsLayer: https://deck.gl/docs/api-reference/geo-layers/trips-layer
- globe.gl: https://globe.gl/
- AISStream API: https://aisstream.io/documentation.html
- AISHub API: https://www.aishub.net/api
- OpenSky API: https://openskynetwork.github.io/opensky-api/
- GDELT DOC 2.0 API: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/amp/
- Global Fishing Watch APIs: https://globalfishingwatch.org/our-apis/documentation
- OpenAerialMap legal / use terms: https://openaerialmap.org/legal
- Mapillary API access: https://help.mapillary.com/hc/en-us/articles/360010234680-Accessing-imagery-and-data-through-the-Mapillary-API
