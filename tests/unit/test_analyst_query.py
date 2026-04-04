"""Unit tests for analyst query and briefing models — Phase 5 Track C."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.models.analyst_query import (
    AnalystQuery,
    BriefingOutput,
    BriefingRequest,
    BriefingSection,
    QueryFieldType,
    QueryFilter,
    QueryOperator,
    QueryResult,
)
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.services.analyst_query_service import AnalystQueryService


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

_POINT = {"type": "Point", "coordinates": [30.0, 45.0]}
_POLY = {
    "type": "Polygon",
    "coordinates": [[[29.0, 44.0], [31.0, 44.0], [31.0, 46.0], [29.0, 46.0], [29.0, 44.0]]],
}


def _make_event(
    source: str = "test-src",
    event_type: EventType = EventType.SHIP_POSITION,
    entity_id: str = "MMSI-111111111",
    confidence: float | None = 0.8,
    attrs: dict | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=make_event_id(source, entity_id, _NOW.isoformat()),
        source=source,
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.VESSEL,
        entity_id=entity_id,
        event_type=event_type,
        event_time=_NOW,
        geometry=_POLY,
        centroid=_POINT,
        confidence=confidence,
        attributes=attrs or {},
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="s3://bucket/test.json"),
        correlation_keys=CorrelationKeys(),
        license=LicenseRecord(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Model tests
# ──────────────────────────────────────────────────────────────────────────────


def test_analyst_query_default_fields():
    q = AnalystQuery(filters=[])
    assert q.query_id  # auto-generated UUID
    assert isinstance(uuid.UUID(q.query_id), uuid.UUID)
    assert q.combine_with == QueryOperator.AND
    assert q.limit == 100
    assert q.include_provenance is True
    assert q.label is None
    assert q.filters == []


def test_analyst_query_custom_fields():
    q = AnalystQuery(
        label="Ship Tracks",
        filters=[],
        combine_with=QueryOperator.OR,
        limit=50,
        include_provenance=False,
    )
    assert q.label == "Ship Tracks"
    assert q.combine_with == QueryOperator.OR
    assert q.limit == 50
    assert q.include_provenance is False


def test_query_filter_event_type():
    f = QueryFilter(field=QueryFieldType.EVENT_TYPE, operator="eq", value="ship_position")
    assert f.field == QueryFieldType.EVENT_TYPE
    assert f.operator == "eq"
    assert f.value == "ship_position"


def test_query_filter_source_type():
    f = QueryFilter(field=QueryFieldType.SOURCE_TYPE, operator="eq", value="telemetry")
    assert f.field == QueryFieldType.SOURCE_TYPE
    assert f.value == "telemetry"


def test_query_filter_entity_id():
    f = QueryFilter(field=QueryFieldType.ENTITY_ID, operator="eq", value="MMSI-123456789")
    assert f.field == QueryFieldType.ENTITY_ID


def test_query_filter_time_range():
    f = QueryFilter(
        field=QueryFieldType.TIME_RANGE,
        operator="within",
        value={"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T23:59:59Z"},
    )
    assert f.field == QueryFieldType.TIME_RANGE
    assert isinstance(f.value, dict)


def test_query_filter_confidence():
    f = QueryFilter(field=QueryFieldType.CONFIDENCE, operator="gte", value=0.7)
    assert f.field == QueryFieldType.CONFIDENCE
    assert f.value == 0.7


def test_query_filter_text():
    f = QueryFilter(field=QueryFieldType.TEXT, operator="contains", value="cargo")
    assert f.field == QueryFieldType.TEXT


def test_briefing_request_defaults_all_sections():
    req = BriefingRequest(title="Test Briefing")
    assert set(req.sections) == set(BriefingSection)
    assert req.classification_label == "UNCLASSIFIED"
    assert req.investigation_id is None
    assert req.query is None


def test_briefing_request_custom_sections():
    req = BriefingRequest(
        title="Partial",
        sections=[BriefingSection.EXECUTIVE_SUMMARY, BriefingSection.TIMELINE],
    )
    assert len(req.sections) == 2
    assert BriefingSection.EXECUTIVE_SUMMARY in req.sections


def test_briefing_output_construction():
    b = BriefingOutput(
        title="Test",
        sections_generated=[BriefingSection.EXECUTIVE_SUMMARY],
        content={"executive_summary": "Summary text."},
        data_summary={"total_events": 5},
        raw_event_count=5,
        confidence_assessment="high",
    )
    assert b.briefing_id
    assert isinstance(uuid.UUID(b.briefing_id), uuid.UUID)
    assert b.raw_event_count == 5
    assert b.confidence_assessment == "high"
    assert b.classification_label == "UNCLASSIFIED"


def test_query_result_construction():
    result = QueryResult(
        query_id=str(uuid.uuid4()),
        total_matched=10,
        returned_count=5,
        events=[],
        sources_cited=["src-a", "src-b"],
        confidence_range=(0.5, 0.9),
    )
    assert result.total_matched == 10
    assert result.returned_count == 5
    assert result.confidence_range == (0.5, 0.9)
    assert len(result.sources_cited) == 2


def test_query_result_empty():
    result = QueryResult(
        query_id=str(uuid.uuid4()),
        total_matched=0,
        returned_count=0,
    )
    assert result.total_matched == 0
    assert result.confidence_range is None
    assert result.events == []


# ──────────────────────────────────────────────────────────────────────────────
# Service tests (isolated — fresh AnalystQueryService each test)
# ──────────────────────────────────────────────────────────────────────────────


def test_execute_query_empty_store(monkeypatch):
    """execute_query with empty store returns empty result."""
    import src.services.analyst_query_service as _aqs_mod

    class _EmptyStore:
        _lock = __import__("threading").Lock()
        _events: dict = {}

        def get(self, eid):
            return None

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _EmptyStore())
    svc = AnalystQueryService()
    q = AnalystQuery(filters=[])
    result = svc.execute_query(q)
    assert result.total_matched == 0
    assert result.returned_count == 0
    assert result.events == []
    assert result.sources_cited == []


def test_execute_query_event_type_filter(monkeypatch):
    """execute_query with EVENT_TYPE filter returns only matching events."""
    import threading
    import src.services.analyst_query_service as _aqs_mod

    ship_event = _make_event(event_type=EventType.SHIP_POSITION, entity_id="MMSI-001")
    air_event = _make_event(
        source="opensky",
        event_type=EventType.AIRCRAFT_POSITION,
        entity_id="ICAO-ABC",
    )

    class _Store:
        _lock = threading.Lock()
        _events = {ship_event.event_id: ship_event, air_event.event_id: air_event}

        def get(self, eid):
            return self._events.get(eid)

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _Store())
    svc = AnalystQueryService()
    q = AnalystQuery(
        filters=[QueryFilter(field=QueryFieldType.EVENT_TYPE, operator="eq", value="ship_position")]
    )
    result = svc.execute_query(q)
    assert result.total_matched == 1
    assert result.events[0]["event_type"] == "ship_position"


def test_generate_briefing_builds_all_sections(monkeypatch):
    """generate_briefing returns content for all requested sections."""
    import threading
    import src.services.analyst_query_service as _aqs_mod

    event = _make_event()

    class _Store:
        _lock = threading.Lock()
        _events = {event.event_id: event}

        def get(self, eid):
            return self._events.get(eid)

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _Store())
    svc = AnalystQueryService()
    req = BriefingRequest(title="Full Briefing", sections=list(BriefingSection))
    briefing = svc.generate_briefing(req)

    assert briefing.title == "Full Briefing"
    assert set(briefing.sections_generated) == set(BriefingSection)
    for section in BriefingSection:
        assert section.value in briefing.content
        assert isinstance(briefing.content[section.value], str)
    assert briefing.raw_event_count >= 0


def test_export_briefing_text_includes_classification(monkeypatch):
    """export_briefing_text wraps output with classification labels."""
    import threading
    import src.services.analyst_query_service as _aqs_mod

    class _EmptyStore:
        _lock = __import__("threading").Lock()
        _events: dict = {}

        def get(self, eid):
            return None

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _EmptyStore())
    svc = AnalystQueryService()
    req = BriefingRequest(
        title="Classified Report",
        classification_label="SECRET//NOFORN",
        sections=[BriefingSection.EXECUTIVE_SUMMARY],
    )
    briefing = svc.generate_briefing(req)
    text = svc.export_briefing_text(briefing)
    assert "SECRET//NOFORN" in text
    assert "EXECUTIVE SUMMARY" in text.upper()


def test_confidence_assessment_high(monkeypatch):
    import threading
    import src.services.analyst_query_service as _aqs_mod

    ev = _make_event(confidence=0.9)

    class _Store:
        _lock = threading.Lock()
        _events = {ev.event_id: ev}

        def get(self, eid):
            return self._events.get(eid)

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _Store())
    svc = AnalystQueryService()
    req = BriefingRequest(title="High Conf", sections=[BriefingSection.EXECUTIVE_SUMMARY])
    briefing = svc.generate_briefing(req)
    assert briefing.confidence_assessment == "high"


def test_confidence_assessment_medium(monkeypatch):
    import threading
    import src.services.analyst_query_service as _aqs_mod

    ev = _make_event(confidence=0.5)

    class _Store:
        _lock = threading.Lock()
        _events = {ev.event_id: ev}

        def get(self, eid):
            return self._events.get(eid)

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _Store())
    svc = AnalystQueryService()
    req = BriefingRequest(title="Med Conf", sections=[BriefingSection.EXECUTIVE_SUMMARY])
    briefing = svc.generate_briefing(req)
    assert briefing.confidence_assessment == "medium"


def test_confidence_assessment_low(monkeypatch):
    import threading
    import src.services.analyst_query_service as _aqs_mod

    ev = _make_event(confidence=0.2)

    class _Store:
        _lock = threading.Lock()
        _events = {ev.event_id: ev}

        def get(self, eid):
            return self._events.get(eid)

    monkeypatch.setattr(_aqs_mod, "get_default_event_store", lambda: _Store())
    svc = AnalystQueryService()
    req = BriefingRequest(title="Low Conf", sections=[BriefingSection.EXECUTIVE_SUMMARY])
    briefing = svc.generate_briefing(req)
    assert briefing.confidence_assessment == "low"
