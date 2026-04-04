# Delivery Plan

This plan is milestone-based, production-oriented, and intentionally conservative. Every phase must end in a deployable, client-visible release. The plan favors thin vertical slices over infrastructure-first overbuild.

## Planning principles

- Do not overbuild.
- Every phase must produce visible user value.
- Every phase must leave the system in a releasable state.
- Architecture work only exists to unblock visible workflows.
- Paid/commercial dependencies are deferred until public/free sources prove workflow value.
- The primary target is a Middle East-capable pilot, not a premature global command center.

## Release roadmap overview

| Phase | Name | Primary outcome | Release type |
|---|---|---|---|
| 0 | Foundation and architecture | Approved architecture, repo structure, canonical model, source strategy, light scaffolding | internal baseline |
| 1 | MVP operational map | First client-usable AOI map with timeline/event search using free/public sources | pilot release |
| 2 | Imagery and context | STAC imagery discovery + GDELT context + historical replay | pilot+ |
| 3 | Maritime and aviation | Ship and aircraft layers with playback trails and source controls | operational beta |
| 4 | Change analytics | First production construction-change workflow with analyst review | limited production |
| 5 | Production hardening | performance, caching, async jobs, resilience, observability, release management | production |

## Milestone map

### Phase 0 milestones
1. Confirm source inventory classification and exclusions.
2. Approve canonical event model.
3. Approve logical architecture and storage design.
4. Create repo conventions, config contract, schemas, ADR baseline.
5. Stand up basic health/metrics/logging skeleton.

### Phase 1 milestones
1. AOI model and AOI CRUD.
2. Basemap + 2D UI shell.
3. STAC catalog search integration.
4. Event search API and source catalog panel.
5. First release packaging and operational checks.

### Phase 2 milestones
1. Historical imagery/timeline correlation UX.
2. GDELT integration and contextual layer.
3. Playback service for non-track event families.
4. Export of AOI timeline results.
5. Analyst validation against reference AOIs.

### Phase 3 milestones
1. AIS connector + canonical ship position events.
2. OpenSky connector + canonical aircraft position events.
3. Track segment materialization and TripsLayer playback.
4. Source toggles / density controls / performance caps.
5. Operational beta release.

### Phase 4 milestones
1. Public imagery compare workflow.
2. Change-detection job skeleton and review UI.
3. Correlation of change candidates with permits/news/tracks.
4. Analyst disposition workflow.
5. Limited production release.

### Phase 5 milestones
1. Caching and async orchestration.
2. source-health dashboards and freshness SLAs.
3. export governance and license-aware filtering.
4. release process, rollback process, load validation.
5. production go-live.

## Dependency graph

```text
Canonical event model
        |
        v
Source adapters -> normalization -> PostGIS/object storage -> query APIs -> UI layers -> playback/analytics
        |                                                              |
        +---------------- observability/security/config ----------------+
```

Critical sequencing dependencies:
- You cannot build trustworthy playback before canonical time handling exists.
- You should not add dense moving-object layers before viewport filtering and performance controls exist.
- You should not add premium providers before license-aware source governance exists.
- You should not invest in change analytics before imagery discovery, temporal alignment, and analyst validation are stable.

## Phase 0 — Foundation and architecture

### Objective
Freeze the architecture decisions required to avoid wasteful implementation and stand up only the scaffolding needed for disciplined delivery.

### Business value
Prevents architecture churn, reduces false starts, and gives leadership and client stakeholders a credible delivery baseline.

### Scope
- architecture pack
- source strategy
- canonical event model
- risk register
- ADR baseline
- repo/folder structure
- config/secrets contract
- observability skeleton

### In scope
- documentation
- schema definition
- basic repo structure
- health/metrics/logging conventions
- source classification

### Out of scope
- full ingestion connectors
- full frontend implementation
- premium provider integrations
- production-scale data retention pipeline

### Source integrations included
None beyond proof-of-access validation or interface spike notes.

### Architecture work included
All major architecture decisions required for Phases 1–2.

### Frontend/backend/data work included
Only scaffolding and interface contracts.

### Testing and validation
- architecture review
- schema review
- source strategy review
- stakeholder walkthrough

### Release criteria
- docs approved
- source recommendations approved
- schema approved
- phase scope boundaries accepted

### Operational readiness criteria
- env/config template exists
- health/logging conventions defined
- risk owners assigned

### Risks
- scope inflation during architecture phase
- pressure to start coding without decisions
- assumptions about local authority data go unvalidated

### Dependencies
- source inventory
- stakeholder review availability

## Phase 1 — MVP operational map

### Objective
Deliver the first client-usable map and timeline workflows using only free/public, Middle East-capable sources.

### Business value
Demonstrates the platform as a real product, not a concept deck.

### Scope
- 2D operational map
- AOI selection
- source catalog visibility
- event/timeline search
- first STAC imagery search
- first export (CSV/GeoJSON)

### In scope features
- authentication optional if single-tenant pilot
- AOI create/save/load
- MapLibre base map
- layer toggles
- STAC imagery search results and footprints
- source metadata panel
- event search API
- simple timeline panel

### Out of scope
- 3D globe as primary surface
- dense track playback
- automated change detection
- heavy analytics
- commercial imagery

### Source integrations included
- Copernicus CDSE
- Earth Search
- NASA GIBS or MPC as supporting catalog/search layer
- GDELT metadata card only if low-risk to include
- selected municipal/ArcGIS sources only where a pilot AOI has real availability

### Architecture work included
- PostGIS schema
- raw object storage structure
- canonical event validation
- source connector base interfaces

### Frontend/backend/data work included
- frontend shell
- AOI and event APIs
- STAC search adapter(s)
- basic normalization pipeline for imagery acquisitions and contextual events

### Testing and validation
- AOI search against at least 3 Middle East reference areas
- timeline filter correctness
- imagery search cross-checks between CDSE and Earth Search on sample AOIs
- map performance on pilot AOI sizes

### Release criteria
- client can save AOI
- client can search imagery intersecting AOI
- client can view timeline results and source details
- exports work for permitted data

### Operational readiness criteria
- health checks
- source freshness indicators for enabled connectors
- basic structured logs
- config documented

### Risks
- public-record availability may be sparse
- STAC provider differences may create confusing result mismatches
- temptation to add 3D before 2D workflows are stable

### Dependencies
- Phase 0 approvals
- one or more validated pilot AOIs

## Phase 2 — Imagery and context release

### Objective
Add historical replay and contextual correlation so analysts can reason about change over time.

### Business value
Moves the product from "map viewer" to "analysis workbench."

### Scope
- synchronized imagery + context timeline
- GDELT integration
- historical replay for event families
- initial compare/export workflows

### In scope features
- 3D globe overview mode (lightweight)
- timeline playback controller
- contextual event layer
- imagery compare metadata workflow
- DuckDB export package for offline analysis

### Out of scope
- continuous streaming tracks at scale
- automated construction scoring
- premium imagery ordering

### Source integrations included
- GDELT
- HLS and Landsat where useful
- Mapillary/OpenAerialMap only for contextual validation when present

### Architecture work included
- replay materialization API
- event partitioning strategy
- source freshness dashboards

### Frontend/backend/data work included
- timeline/playback UX
- contextual enrichment APIs
- export/report jobs

### Testing and validation
- replay correctness on 7-day and 30-day windows
- event ordering under late-arrival scenarios
- export reproducibility using DuckDB

### Release criteria
- analysts can replay a 30-day AOI timeline
- imagery and contextual events remain synchronized
- export packages are reproducible

### Operational readiness criteria
- late-arrival handling implemented
- replay latency within agreed threshold for pilot AOIs
- source error visibility

### Risks
- GDELT noise may create false confidence
- replay UX can become cluttered
- export sizes may grow quickly

### Dependencies
- stable canonical event model
- stable AOI/time query API

## Phase 3 — Maritime and aviation release

### Objective
Add moving-object feeds and track playback in a controlled, bounded manner.

### Business value
Unlocks the sample-video-style movement and playback capability that users expect.

### Scope
- maritime integration
- aviation integration
- track materialization
- deck.gl TripsLayer playback
- density controls and source toggles

### In scope features
- AISStream backend relay
- OpenSky connector
- optional AISHub or ADS-B Exchange secondary feed
- point and trail visualization
- source filters
- live window + historical window modes

### Out of scope
- global unconstrained live tracking
- premium satellite-AIS or Aireon
- multi-source record-of-truth arbitration at global scale

### Source integrations included
- AISStream
- OpenSky
- optional AISHub / ADS-B Exchange for comparative pilot testing

### Architecture work included
- streaming/polling connector base
- track segment builder
- retention and thinning policy for high-volume telemetry

### Frontend/backend/data work included
- moving-object layer engine
- playback API for tracks
- viewport-aware query limits

### Testing and validation
- bounded AOI live tests
- playback smoothness tests
- browser performance under dense but realistic windows
- duplicate/late-arrival telemetry tests

### Release criteria
- client can view vessel and aircraft activity in/near AOI
- client can replay tracks with trails
- UI remains responsive at defined pilot density thresholds

### Operational readiness criteria
- source-specific reconnect and throttling policies
- ingest lag monitoring
- data-retention policy for telemetry

### Risks
- public feed coverage gaps
- UI performance collapse under dense tracks
- confusion between observed and interpolated movement

### Dependencies
- replay service
- performance guardrails
- source licensing review

## Phase 4 — Change analytics release

### Objective
Deliver the first production construction-change workflow.

### Business value
Creates the first workflow that directly answers the client's core construction-monitoring need.

### Scope
- imagery pair selection
- change-candidate generation
- correlation with permits/news/tracks
- analyst review and disposition

### In scope features
- AOI-specific change jobs
- candidate scoring
- review queue
- evidence panel linking source events and imagery

### Out of scope
- full automation without review
- highly customized ML pipelines for every sensor/provider
- premium imagery ordering loops

### Source integrations included
- public imagery first
- public records/context sources
- optional premium imagery only if approved by business case

### Architecture work included
- async job execution
- derived event storage for change candidates
- analyst feedback capture

### Frontend/backend/data work included
- compare UI
- change job APIs
- review workflow
- evidence export

### Testing and validation
- analyst review on curated AOIs
- precision/recall style operational evaluation
- false-positive review especially for cloud/shadow and SAR artifacts

### Release criteria
- analysts can run, review, and disposition change candidates
- evidence chain is exportable
- known false-positive classes are documented

### Operational readiness criteria
- async jobs observable and retryable
- review outcomes persisted
- cost controls for any premium compute/services

### Risks
- public imagery resolution may be insufficient for small sites
- algorithmic false positives can erode trust
- pressure to skip analyst review

### Dependencies
- mature imagery search and playback
- analyst champion availability
- agreed operational evaluation criteria

## Phase 5 — Production hardening

### Objective
Turn the pilot into a resilient operational service.

### Business value
Reduces failure risk and prepares for broader adoption.

### Scope
- caching
- async orchestration
- resilience
- observability expansion
- release/rollback discipline
- license-aware export controls

### In scope features
- Redis or equivalent cache
- worker queue
- background materialization
- source freshness dashboards
- release runbooks
- backup/restore drills

### Out of scope
- speculative enterprise features with no customer pull
- full warehouse if operational database still suffices

### Source integrations included
Only those proven valuable earlier.

### Architecture work included
- failover/backup
- throttling hardening
- retention tuning
- cost/usage controls

### Frontend/backend/data work included
- performance tuning
- pagination/simplification
- job UX polish
- admin/source health panels

### Testing and validation
- load tests
- fail/restart drills
- rollback drills
- export governance tests

### Release criteria
- agreed performance targets met
- rollback validated
- monitoring and alerting live
- runbooks complete

### Operational readiness criteria
- on-call handoff possible
- dashboard coverage adequate
- data retention and provider restrictions enforced

### Risks
- hardening work can expand endlessly
- warehouse temptation before justified
- paid-source costs can creep without controls

### Dependencies
- usage data from earlier phases
- operations owner

## Sequencing rationale

The sequencing is deliberate:
1. Architecture first because source and licensing uncertainty is high.
2. 2D AOI workflows before 3D because they are analytically useful.
3. STAC and context before telemetry because imagery and context define the construction-monitoring backbone.
4. Track playback only after time alignment and performance controls exist.
5. Change analytics only after baseline workflows are trusted.
6. Hardening after real usage exposes the bottlenecks worth fixing.

## Intentional deferrals

Defer until justified:
- global unconstrained real-time ingestion
- enterprise lakehouse/warehouse
- commercial imagery ordering
- complex ML before analyst-reviewed heuristics
- multi-tenant entitlements
- advanced alerting/watchlists
