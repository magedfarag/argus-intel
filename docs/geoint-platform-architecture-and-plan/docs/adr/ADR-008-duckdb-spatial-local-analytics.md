# ADR-008 — DuckDB Spatial is the default local analytics tool

## Status
Accepted

## Context
Analysts frequently need to run ad-hoc spatial queries against exported AOI datasets — aggregating events by geometry, replaying tracks, cross-referencing STAC acquisition dates against permit records — without standing up a full PostGIS stack locally.

Options considered:
1. **QGIS / GIS desktop tools** — powerful but require configuration and don't support SQL-native workflows analysts already know.
2. **Jupyter + GeoPandas** — Python-centric; heavyweight install; slower for large in-memory datasets.
3. **DuckDB + DuckDB Spatial** — lightweight single binary, SQL-native, supports Parquet + GeoParquet via `ST_*` functions, integrates with Python notebooks and standalone SQL shells.

## Decision
Use **DuckDB Spatial** as the default tool for offline analyst workflows:
- Export service produces Parquet/GeoParquet files named by AOI and time window.
- A DuckDB analyst template (`docs/v2/duckdb-template.md`) provides 12 reference queries covering event replay, track aggregation, coverage checking, and cross-source counting.
- No DuckDB instance is required in the production deployment; it is a local analyst tool only.

## Consequences
- `src/services/parquet_export.py` — produces DuckDB Spatial-compatible Parquet with WKT geometry.
- `docs/v2/duckdb-template.md` — analyst template with 12 sample queries; canonical reference.
- `ExportPanel.tsx` exposes GeoJSON + CSV export; Parquet endpoint (`/api/v1/exports?format=parquet`) follows the same job-polling contract.
- No warehouse architecture is introduced in Phases 0–5; DuckDB remains the analyst boundary.
- If scale demands a warehouse, the Parquet export format enables a direct transition to Delta Lake, Apache Iceberg, or BigQuery without re-engineering the ingestion layer.

## Implementation notes
- `src/services/parquet_export.py` — AOI event Parquet export
- `docs/v2/duckdb-template.md` — 12 analyst queries
- `tests/unit/test_parquet_export.py` — reproducibility tests (24 tests)
