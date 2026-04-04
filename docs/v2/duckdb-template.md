# DuckDB Offline Analyst Workflow — P2-4.2

This template demonstrates how to load and query the Parquet export package
produced by `ParquetExportService` (see `src/services/parquet_export.py`).

## Prerequisites

```bash
pip install duckdb        # >= 0.10
# DuckDB Spatial extension (installed from inside DuckDB on first use)
```

## Quick start

### 1. Export events via the API

```bash
# Trigger a Parquet export for an AOI (requires a running server)
curl -s -X POST http://localhost:8000/api/v1/exports \
  -H "Content-Type: application/json" \
  -d '{
    "search": {
      "aoi_id": "pilot-riyadh-neom-northgate",
      "start_time": "2026-01-01T00:00:00Z",
      "end_time":   "2026-04-01T00:00:00Z"
    },
    "format": "parquet"
  }' | jq .download_url
```

### 2. Open in DuckDB

```sql
-- Load the Spatial extension (once per session)
INSTALL spatial;
LOAD spatial;

-- Point to the downloaded file (adjust path)
SET variable parquet_path = '/path/to/export.parquet';

-- Read all events
SELECT * FROM read_parquet(getvariable('parquet_path')) LIMIT 5;
```

## Common analyst queries

### Event counts by source and type
```sql
SELECT
    source,
    event_type,
    COUNT(*) AS n_events,
    MIN(event_time) AS earliest,
    MAX(event_time) AS latest
FROM read_parquet(getvariable('parquet_path'))
GROUP BY 1, 2
ORDER BY n_events DESC;
```

### All events within a 10 km radius of Riyadh city centre
```sql
WITH events AS (
    SELECT *,
        ST_GeomFromText(geometry_wkt)       AS geom,
        ST_Point(46.6753, 24.8000)           AS riyadh
    FROM read_parquet(getvariable('parquet_path'))
)
SELECT
    event_id, source, event_type, event_time, centroid_lon, centroid_lat
FROM events
WHERE ST_Distance_Sphere(geom, riyadh) <= 10000   -- 10 km in metres
ORDER BY event_time;
```

### Timeline: daily imagery acquisition counts
```sql
SELECT
    strftime(event_time, '%Y-%m-%d')   AS day,
    COUNT(*)                            AS imagery_scenes,
    AVG(CAST(json_extract(attributes, '$.cloud_cover_pct') AS DOUBLE)) AS avg_cloud_pct
FROM read_parquet(getvariable('parquet_path'))
WHERE event_type = 'imagery_acquisition'
GROUP BY 1
ORDER BY 1;
```

### Ship positions near Dubai Creek Harbour
```sql
SELECT
    event_id,
    json_extract(attributes, '$.mmsi')         AS mmsi,
    json_extract(attributes, '$.vessel_name')  AS vessel_name,
    json_extract(attributes, '$.speed_kn')     AS speed_kn,
    centroid_lon, centroid_lat, event_time
FROM read_parquet(getvariable('parquet_path'))
WHERE event_type = 'ship_position'
  AND centroid_lon BETWEEN 55.27 AND 55.43
  AND centroid_lat BETWEEN 24.98 AND 25.28
ORDER BY event_time;
```

### Aircraft activity during a time window
```sql
SELECT
    json_extract(attributes, '$.callsign')       AS callsign,
    json_extract(attributes, '$.origin_country') AS country,
    json_extract(attributes, '$.baro_altitude_m') AS altitude_m,
    centroid_lon, centroid_lat, event_time
FROM read_parquet(getvariable('parquet_path'))
WHERE event_type  = 'aircraft_position'
  AND event_time >= '2026-03-01T00:00:00+00:00'
  AND event_time <  '2026-04-01T00:00:00+00:00'
ORDER BY event_time;
```

### Quality flag filter — exclude low-quality imagery
```sql
SELECT *
FROM read_parquet(getvariable('parquet_path'))
WHERE event_type = 'imagery_acquisition'
  AND NOT json_contains(quality_flags, '"low-quality"')
  AND CAST(json_extract(attributes, '$.cloud_cover_pct') AS DOUBLE) < 20.0;
```

### Export filtered subset to a new Parquet file
```sql
COPY (
    SELECT * FROM read_parquet(getvariable('parquet_path'))
    WHERE source = 'earth-search'
      AND event_type = 'imagery_acquisition'
) TO '/path/to/filtered.parquet' (FORMAT PARQUET);
```

## Column reference

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | STRING | Deterministic SHA-256 event identifier |
| `source` | STRING | Provider code (e.g. `earth-search`, `opensky`) |
| `source_type` | STRING | `imagery_catalog`, `telemetry`, `context_feed`, … |
| `entity_type` | STRING | `imagery_scene`, `vessel`, `aircraft`, … |
| `entity_id` | STRING | Source-native identifier |
| `event_type` | STRING | `imagery_acquisition`, `ship_position`, … |
| `event_time` | STRING | ISO-8601 UTC timestamp |
| `time_start` | STRING | Interval start (optional) |
| `time_end` | STRING | Interval end (optional) |
| `ingested_at` | STRING | ISO-8601 UTC ingest timestamp |
| `geometry_wkt` | STRING | WKT geometry — use `ST_GeomFromText()` in DuckDB Spatial |
| `centroid_lon` | DOUBLE | Centroid longitude |
| `centroid_lat` | DOUBLE | Centroid latitude |
| `confidence` | DOUBLE | [0.0–1.0]; -1.0 = not set |
| `quality_flags` | STRING | JSON array of string flags |
| `attributes` | STRING | JSON object — schema varies by event_type |
| `license_access_tier` | STRING | `public` / `restricted` / `commercial` |
| `license_redistribution` | STRING | `allowed` / `not-allowed` / `check-provider-terms` |
| `normalization_warnings` | STRING | JSON array of warning strings |
| `provenance_raw_source_ref` | STRING | S3 path or URL of original raw payload |
