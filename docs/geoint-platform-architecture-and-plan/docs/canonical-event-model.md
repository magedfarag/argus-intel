# Canonical Event Model

This document defines the normalized event schema for the platform. The purpose is to preserve source fidelity while giving engineering and analytics one predictable structure for search, replay, and correlation.

## 1. Design goals

- Normalize heterogeneous feeds without deleting source-specific meaning.
- Support point events, time ranges, and tracks.
- Support both observed facts and derived/model-generated events.
- Preserve provenance, licensing, and confidence.
- Be stable enough for APIs, search, and analytics, while extensible through `attributes`.

## 2. Event families covered

- `imagery_acquisition`
- `imagery_detection`
- `change_detection`
- `ship_position`
- `ship_track_segment`
- `aircraft_position`
- `aircraft_track_segment`
- `permit_event`
- `inspection_event`
- `project_event`
- `complaint_event`
- `contextual_event`
- `system_health_event`

## 3. Normative schema

```json
{
  "event_id": "evt_cdse_s2_20260401T102233Z_abc123",
  "source": "copernicus-cdse",
  "source_type": "imagery_catalog",
  "entity_type": "imagery_scene",
  "entity_id": "S2A_MSIL2A_20260401T102233_N...",
  "event_type": "imagery_acquisition",
  "event_time": "2026-04-01T10:22:33Z",
  "time_start": "2026-04-01T10:22:33Z",
  "time_end": "2026-04-01T10:22:33Z",
  "geometry": {
    "type": "Polygon",
    "coordinates": []
  },
  "centroid": {
    "type": "Point",
    "coordinates": [46.6753, 24.7136]
  },
  "altitude_m": null,
  "depth_m": null,
  "confidence": 0.92,
  "quality_flags": ["official-source", "cloud-sensitive"],
  "attributes": {},
  "normalization": {
    "schema_version": "1.0.0",
    "normalized_by": "connector.cdse.stac",
    "normalization_warnings": [],
    "dedupe_key": "..."
  },
  "provenance": {
    "raw_source_ref": "s3://bucket/raw/cdse/....json",
    "source_record_id": "original-provider-id",
    "source_record_version": "etag-or-hash",
    "source_url": "https://..."
  },
  "ingested_at": "2026-04-03T09:15:11Z",
  "first_seen_at": "2026-04-03T09:15:11Z",
  "last_seen_at": "2026-04-03T09:15:11Z",
  "correlation_keys": {
    "aoi_ids": ["aoi_riyadh_01"],
    "mmsi": null,
    "imo": null,
    "icao24": null,
    "callsign": null,
    "permit_id": null,
    "place_key": "SA-RIYADH"
  },
  "license": {
    "access_tier": "public",
    "commercial_use": "allowed-with-terms",
    "redistribution": "check-provider-terms",
    "attribution_required": true
  }
}
```

## 4. Required fields

### Identity
- `event_id`: deterministic internal identifier.
- `source`: normalized provider/source code.
- `source_type`: `imagery_catalog`, `telemetry`, `registry`, `public_record`, `context_feed`, `derived`.
- `entity_type`: type of object the event refers to.
- `entity_id`: source-native or synthesized stable identifier if available.

### Time
- `event_time`: primary event timestamp in UTC.
- `time_start`, `time_end`: required when event spans an interval.
- `ingested_at`: platform ingestion timestamp.
- `first_seen_at`, `last_seen_at`: for late-arriving or updated records.

### Space
- `geometry`: canonical GeoJSON geometry.
- `centroid`: GeoJSON Point.
- `altitude_m`: for aircraft and 3D contexts.
- `depth_m`: reserved for future underwater/subsurface use.

### Quality and provenance
- `confidence`: 0.0–1.0, or null if not meaningful.
- `quality_flags`: string list.
- `normalization`: schema metadata and warnings.
- `provenance`: raw source references and original IDs.
- `license`: access and reuse metadata.

### Flexible payload
- `attributes`: source-specific normalized fields that do not belong in the common top-level contract.
- `correlation_keys`: identifiers or keys used for linking.

## 5. Recommended event-type-specific attributes

### Imagery acquisition
- `collection`
- `platform`
- `sensor`
- `resolution_m`
- `cloud_cover`
- `polarization` (SAR)
- `orbit_direction`
- `stac_item_id`

### Change detection
- `change_score`
- `change_class`
- `before_scene_id`
- `after_scene_id`
- `review_status`
- `evidence_asset_refs`

### Ship position
- `mmsi`
- `imo`
- `ship_name`
- `callsign`
- `course_deg`
- `heading_deg`
- `speed_knots`
- `nav_status`
- `destination`
- `draught_m`
- `vessel_type`
- `cargo_type` (nullable)

### Ship track segment
- `track_point_count`
- `start_position_ref`
- `end_position_ref`
- `distance_nm`
- `avg_speed_knots`

### Aircraft position
- `icao24`
- `callsign`
- `registration`
- `baro_altitude_m`
- `geo_altitude_m`
- `ground_speed_mps`
- `vertical_rate_mps`
- `squawk`

### Permit / inspection / project events
- `permit_id`
- `authority`
- `record_type`
- `status`
- `parcel_id`
- `project_name`
- `applicant`
- `value_estimate`
- `inspection_result`

### Contextual events
- `gdelt_id`
- `theme_codes`
- `tone`
- `language`
- `source_domain`
- `headline`
- `actors`
- `place_mentions`

## 6. Time alignment strategy

### Standardization
- Convert all timestamps to UTC at ingest.
- Preserve original source-local timestamp in `attributes.source_local_time` when provided.
- For date-only records, store noon UTC only if forced; otherwise keep the date range and mark `quality_flags += ["date-only"]`.

### Replay alignment
- Use event time for ordering.
- Materialize playback frames into time buckets only on demand.
- Never fabricate intermediate points for sparse telemetry without explicitly marking them as interpolated.

### Interpolation
Allowed:
- path smoothing for visualization of dense telemetry where timestamps are sufficiently frequent.
- linear interpolation for short gaps in continuous telemetry, flagged as `interpolated`.

Not allowed by default:
- interpolating imagery acquisitions, permits, or contextual events.
- treating one-hour gridded presence data as continuous minute-by-minute tracks.

## 7. Late-arriving data handling

- Accept updates and store last-seen version.
- Use source-native version/etag/hash where available.
- Recompute derived correlations only for affected partitions.
- Maintain `quality_flags += ["late-arrival"]` when event-time is older than configured threshold relative to ingest time.

## 8. Deduplication strategy

### Deterministic
If provider offers a stable event or record ID, use it.

### Heuristic fallback
Use a dedupe key composed from:
- source
- entity identifier(s)
- event type
- rounded event time bucket
- rounded centroid / geometry hash

Keep duplicates as provenance edges where needed. Do not discard valuable alternate-source observations blindly.

## 9. Source confidence ranking

Default ranking for analysis:
1. official authority records
2. official EO mission metadata
3. direct telemetry from transparent networks
4. curated aggregators
5. inferred/model-derived events
6. media/contextual feeds

This ranking is only a prior. Analysts may override it for a given workflow.

## 10. Correlation strategy

Correlation occurs across shared AOI + time window + identifiers.

### Hard links
- same MMSI / IMO / icao24 / permit ID / STAC item ID

### Soft links
- same AOI and nearby time bucket
- same place, actor, or project name
- same parcel/building footprint intersecting imagery change region

Soft links must expose confidence and explanation.

## 11. CRS and geometry rules

- Store canonical geometry in EPSG:4326.
- Preserve source CRS in `attributes.source_crs` if not EPSG:4326.
- Reproject at ingest for canonical storage.
- Track operations that can distort geometry precision, especially for raster footprint simplification.

## 12. Quality controls

Validation rules:
- required fields present
- valid GeoJSON geometry
- valid UTC timestamps
- confidence between 0 and 1
- source license classification set
- raw provenance reference present for persisted records

## 13. Schema evolution

- version the schema via `normalization.schema_version`
- additive changes only within minor versions
- breaking changes require migration plan and ADR
