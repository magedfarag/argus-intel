"""Unit tests for the Parquet export service — P2-4.4.

Tests verify:
- Correct serialisation of CanonicalEvents to Parquet bytes
- DuckDB-compatible WKT geometry column
- License filtering (redistribution=not-allowed excluded by default)
- Empty export when all events are filtered
- Round-trip: Parquet bytes can be loaded back by pyarrow/DuckDB
- Reproducibility: same inputs → same Parquet schema (row count + columns)
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pytest

from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.services.parquet_export import (
    ParquetExportError,
    ParquetExportResult,
    ParquetExportService,
    _geojson_to_wkt,
    _geojson_point_to_wkt,
    _event_to_row,
)

pyarrow = pytest.importorskip("pyarrow", reason="pyarrow not installed")
pq = pytest.importorskip("pyarrow.parquet", reason="pyarrow not installed")


# ── Fixtures ──────────────────────────────────────────────────────────────────

_T0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [46.65, 24.77],
        [46.70, 24.77],
        [46.70, 24.82],
        [46.65, 24.82],
        [46.65, 24.77],
    ]],
}
_POINT = {"type": "Point", "coordinates": [46.675, 24.800]}


def _make_event(
    source: str = "test-source",
    redistribution: str = "allowed",
    event_type: EventType = EventType.IMAGERY_ACQUISITION,
    entity_type: EntityType = EntityType.IMAGERY_SCENE,
    geometry: dict | None = None,
) -> CanonicalEvent:
    ts = datetime.now(timezone.utc).isoformat()
    return CanonicalEvent(
        event_id=make_event_id(source, "e1", ts),
        source=source,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=entity_type,
        entity_id="e1",
        event_type=event_type,
        event_time=_T0,
        geometry=geometry or _POLYGON,
        centroid=_POINT,
        attributes={"platform": "Sentinel-2A"},
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="s3://test/raw"),
        license=LicenseRecord(redistribution=redistribution),
    )


# ── WKT conversion helpers ────────────────────────────────────────────────────

class TestGeojsonToWkt:
    def test_point(self) -> None:
        wkt = _geojson_point_to_wkt({"type": "Point", "coordinates": [46.5, 24.8]})
        assert wkt == "POINT (46.5 24.8)"

    def test_polygon(self) -> None:
        wkt = _geojson_to_wkt(_POLYGON)
        assert wkt.startswith("POLYGON ((")
        assert "46.65 24.77" in wkt

    def test_point_via_generic(self) -> None:
        wkt = _geojson_to_wkt({"type": "Point", "coordinates": [10.0, 20.0]})
        assert wkt == "POINT (10.0 20.0)"

    def test_multipolygon(self) -> None:
        mp = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
        }
        wkt = _geojson_to_wkt(mp)
        assert wkt.startswith("MULTIPOLYGON")

    def test_missing_type_returns_empty_collection(self) -> None:
        wkt = _geojson_to_wkt({})
        assert "EMPTY" in wkt or wkt == "GEOMETRYCOLLECTION EMPTY"

    def test_malformed_coords_returns_point_fallback(self) -> None:
        wkt = _geojson_point_to_wkt({"type": "Point", "coordinates": []})
        assert wkt == "POINT (0 0)"


# ── Row flattening ────────────────────────────────────────────────────────────

class TestEventToRow:
    def test_required_columns_present(self) -> None:
        row = _event_to_row(_make_event())
        required = [
            "event_id", "source", "source_type", "entity_type", "event_type",
            "event_time", "geometry_wkt", "centroid_lon", "centroid_lat",
            "confidence", "quality_flags", "attributes",
            "license_access_tier", "license_redistribution",
            "normalization_warnings", "provenance_raw_source_ref",
        ]
        for col in required:
            assert col in row, f"Missing column: {col}"

    def test_centroid_coords_extracted(self) -> None:
        row = _event_to_row(_make_event())
        assert row["centroid_lon"] == pytest.approx(46.675)
        assert row["centroid_lat"] == pytest.approx(24.800)

    def test_attributes_is_json(self) -> None:
        row = _event_to_row(_make_event())
        attrs = json.loads(row["attributes"])
        assert attrs.get("platform") == "Sentinel-2A"

    def test_quality_flags_is_json(self) -> None:
        row = _event_to_row(_make_event())
        flags = json.loads(row["quality_flags"])
        assert isinstance(flags, list)

    def test_geometry_wkt_for_polygon(self) -> None:
        row = _event_to_row(_make_event())
        assert row["geometry_wkt"].startswith("POLYGON")

    def test_no_confidence_uses_sentinel(self) -> None:
        e = _make_event()
        row = _event_to_row(e)
        # confidence is None → -1.0 sentinel
        assert row["confidence"] == -1.0


# ── ParquetExportService ──────────────────────────────────────────────────────

class TestParquetExportService:
    def setup_method(self) -> None:
        self.svc = ParquetExportService()

    def test_basic_export_returns_bytes(self) -> None:
        events = [_make_event()]
        result = self.svc.export_events(events)
        assert isinstance(result, ParquetExportResult)
        assert result.parquet_bytes
        assert result.event_count == 1
        assert result.size_bytes > 0

    def test_parquet_schema_has_expected_columns(self) -> None:
        events = [_make_event()]
        result = self.svc.export_events(events)
        table = pq.read_table(io.BytesIO(result.parquet_bytes))
        assert "event_id" in table.schema.names
        assert "geometry_wkt" in table.schema.names
        assert "centroid_lon" in table.schema.names
        assert "centroid_lat" in table.schema.names
        assert "attributes" in table.schema.names

    def test_license_filter_excludes_restricted(self) -> None:
        e1 = _make_event(redistribution="allowed")
        e2 = _make_event(redistribution="not-allowed")
        result = self.svc.export_events([e1, e2])
        # Only e1 should be included
        assert result.event_count == 1

    def test_include_restricted_flag(self) -> None:
        e1 = _make_event(redistribution="allowed")
        e2 = _make_event(redistribution="not-allowed")
        result = self.svc.export_events([e1, e2], include_restricted=True)
        assert result.event_count == 2

    def test_empty_event_list_produces_valid_parquet(self) -> None:
        result = self.svc.export_events([])
        assert result.event_count == 0
        assert result.parquet_bytes
        table = pq.read_table(io.BytesIO(result.parquet_bytes))
        assert table.num_rows == 0

    def test_all_events_filtered_produces_empty_parquet(self) -> None:
        events = [_make_event(redistribution="not-allowed")]
        result = self.svc.export_events(events)
        assert result.event_count == 0
        table = pq.read_table(io.BytesIO(result.parquet_bytes))
        assert table.num_rows == 0

    def test_multiple_events(self) -> None:
        events = [_make_event(source=f"src-{i}") for i in range(10)]
        result = self.svc.export_events(events)
        assert result.event_count == 10
        table = pq.read_table(io.BytesIO(result.parquet_bytes))
        assert table.num_rows == 10

    def test_aoi_id_recorded_in_result(self) -> None:
        events = [_make_event()]
        result = self.svc.export_events(events, aoi_id="pilot-riyadh")
        assert result.aoi_id == "pilot-riyadh"

    def test_exported_at_is_utc(self) -> None:
        result = self.svc.export_events([_make_event()])
        assert result.exported_at.tzinfo is not None

    def test_reproducibility_same_row_count(self) -> None:
        """Same inputs produce the same row count and column layout."""
        events = [_make_event(source=f"s{i}") for i in range(5)]
        r1 = self.svc.export_events(events)
        r2 = self.svc.export_events(events)
        t1 = pq.read_table(io.BytesIO(r1.parquet_bytes))
        t2 = pq.read_table(io.BytesIO(r2.parquet_bytes))
        assert t1.num_rows == t2.num_rows
        assert t1.schema.names == t2.schema.names

    def test_geometry_wkt_readable_by_parquet(self) -> None:
        """geometry_wkt column contains valid WKT strings."""
        events = [_make_event()]
        result = self.svc.export_events(events)
        table = pq.read_table(io.BytesIO(result.parquet_bytes))
        wkt = table.column("geometry_wkt")[0].as_py()
        assert wkt.startswith("POLYGON")

    def test_point_geometry_event(self) -> None:
        e = _make_event(geometry={"type": "Point", "coordinates": [55.35, 25.20]})
        result = self.svc.export_events([e])
        table = pq.read_table(io.BytesIO(result.parquet_bytes))
        wkt = table.column("geometry_wkt")[0].as_py()
        assert wkt.startswith("POINT")
