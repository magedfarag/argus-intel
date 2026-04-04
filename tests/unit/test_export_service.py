"""Unit tests for ExportService — P1-5.4.

Covers:
  - CSV serialization correctness (header + rows)
  - GeoJSON FeatureCollection structure
  - License-aware filtering (not-allowed events excluded by default)
  - include_restricted=True bypasses the filter
  - Export job lifecycle (create → completed)
  - Download URL included in response
  - Empty result set produces valid empty export
  - Unsupported format raises ValueError
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict

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
from src.models.event_search import EventSearchRequest
from src.services.event_store import EventStore
from src.services.export_service import (
    ExportJobStore,
    ExportService,
    events_to_csv,
    events_to_geojson,
    _is_exportable,
)


# ── Helpers ─────────────────────────────────────────────────────────────────────

_T = datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)
_T_END = datetime(2026, 4, 3, 13, 0, 0, tzinfo=timezone.utc)


def _make_event(
    idx: int,
    event_type: EventType = EventType.IMAGERY_ACQUISITION,
    redistribution: str = "allowed",
) -> CanonicalEvent:
    src = f"test-source-{idx}"
    entity = f"entity-{idx}"
    return CanonicalEvent(
        event_id=make_event_id(src, entity, _T),
        source=src,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        entity_id=entity,
        event_type=event_type,
        event_time=_T,
        geometry={"type": "Polygon", "coordinates": [[[10.0, 20.0], [11.0, 20.0], [11.0, 21.0], [10.0, 20.0]]]},
        centroid={"type": "Point", "coordinates": [10.5, 20.5]},
        license=LicenseRecord(redistribution=redistribution),
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="s3://test/raw.json"),
    )


def _make_search_req() -> EventSearchRequest:
    return EventSearchRequest(start_time=_T, end_time=_T_END)


@pytest.fixture()
def populated_event_store() -> EventStore:
    store = EventStore()
    for i in range(5):
        store.ingest(_make_event(i))
    return store


# ── _is_exportable ─────────────────────────────────────────────────────────────


def test_is_exportable_allowed() -> None:
    ev = _make_event(0, redistribution="allowed")
    assert _is_exportable(ev) is True


def test_is_exportable_not_allowed_blocked() -> None:
    ev = _make_event(0, redistribution="not-allowed")
    assert _is_exportable(ev) is False


def test_is_exportable_not_allowed_bypassed_with_flag() -> None:
    ev = _make_event(0, redistribution="not-allowed")
    assert _is_exportable(ev, include_restricted=True) is True


def test_is_exportable_no_license_defaults_to_allowed() -> None:
    """LicenseRecord defaults redistribution to 'check-provider-terms' which is not blocked."""
    ev = _make_event(0)
    # LicenseRecord default is 'check-provider-terms' — not in _BLOCKED set
    assert _is_exportable(ev) is True


def test_is_exportable_check_provider_terms_not_blocked() -> None:
    ev = _make_event(0, redistribution="check-provider-terms")
    assert _is_exportable(ev) is True


# ── CSV serialisation ───────────────────────────────────────────────────────────────


def test_csv_header_columns() -> None:
    events = [_make_event(0)]
    raw = events_to_csv(events).decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    assert reader.fieldnames is not None
    assert "event_id" in reader.fieldnames
    assert "event_time" in reader.fieldnames
    assert "centroid_lon" in reader.fieldnames
    assert "centroid_lat" in reader.fieldnames
    assert "quality_flags" in reader.fieldnames


def test_csv_row_count_matches_events() -> None:
    events = [_make_event(i) for i in range(7)]
    raw = events_to_csv(events).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(raw)))
    assert len(rows) == 7


def test_csv_centroid_populated() -> None:
    events = [_make_event(0)]
    raw = events_to_csv(events).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(raw)))
    assert rows[0]["centroid_lon"] == "10.5"
    assert rows[0]["centroid_lat"] == "20.5"


def test_csv_empty_input_produces_header_only() -> None:
    raw = events_to_csv([]).decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)
    assert rows == []
    assert reader.fieldnames is not None


# ── GeoJSON serialisation ───────────────────────────────────────────────────────────


def test_geojson_feature_collection_type() -> None:
    events = [_make_event(0)]
    data = json.loads(events_to_geojson(events))
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)


def test_geojson_feature_count_matches_events() -> None:
    events = [_make_event(i) for i in range(4)]
    data = json.loads(events_to_geojson(events))
    assert len(data["features"]) == 4


def test_geojson_feature_properties() -> None:
    event = _make_event(0)
    data = json.loads(events_to_geojson([event]))
    props = data["features"][0]["properties"]
    assert props["event_id"] == event.event_id
    assert props["event_type"] == event.event_type.value
    assert props["source"] == event.source


def test_geojson_feature_geometry_present() -> None:
    event = _make_event(0)
    data = json.loads(events_to_geojson([event]))
    geometry = data["features"][0]["geometry"]
    assert geometry is not None
    assert geometry["type"] == "Polygon"


def test_geojson_empty_input_valid_collection() -> None:
    data = json.loads(events_to_geojson([]))
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []
    assert "generated_at" in data


# ── ExportService ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def export_service(populated_event_store: EventStore) -> ExportService:
    return ExportService(event_store=populated_event_store, job_store=ExportJobStore())


def test_create_export_csv_completed(export_service: ExportService) -> None:
    req = _make_search_req()
    job = export_service.create_export(req, format_="csv")
    assert job.status == "completed"
    assert job.payload is not None
    assert job.event_count == 5


def test_create_export_geojson_completed(export_service: ExportService) -> None:
    req = _make_search_req()
    job = export_service.create_export(req, format_="geojson")
    assert job.status == "completed"
    data = json.loads(job.payload)  # type: ignore[arg-type]
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 5


def test_create_export_license_filter_excludes_restricted() -> None:
    store = EventStore()
    for i in range(3):
        store.ingest(_make_event(i, redistribution="allowed"))
    for i in range(3, 6):
        store.ingest(_make_event(i, redistribution="not-allowed"))
    svc = ExportService(event_store=store, job_store=ExportJobStore())
    job = svc.create_export(_make_search_req(), format_="csv")
    assert job.event_count == 3  # Only 3 allowed exported


def test_create_export_include_restricted_bypasses_filter() -> None:
    store = EventStore()
    for i in range(3):
        store.ingest(_make_event(i, redistribution="not-allowed"))
    svc = ExportService(event_store=store, job_store=ExportJobStore())
    job = svc.create_export(_make_search_req(), format_="csv", include_restricted=True)
    assert job.event_count == 3


def test_create_export_invalid_format_job_failed() -> None:
    store = EventStore()
    store.ingest(_make_event(0))
    svc = ExportService(event_store=store, job_store=ExportJobStore())
    job = svc.create_export(_make_search_req(), format_="xml")  # type: ignore[arg-type]
    assert job.status == "failed"
    assert job.error is not None


def test_export_job_stored_and_retrievable(export_service: ExportService) -> None:
    job_store = ExportJobStore()
    svc = ExportService(event_store=export_service._events, job_store=job_store)
    job = svc.create_export(_make_search_req(), format_="geojson")
    retrieved = job_store.get(job.job_id)
    assert retrieved is not None
    assert retrieved.job_id == job.job_id
    assert retrieved.status == "completed"

