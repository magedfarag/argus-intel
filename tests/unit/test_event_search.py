"""Unit tests for event search API and event store (P1-4.7 — ≥10 tests)."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.events import router as events_router, _store
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
from src.models.event_search import EventSearchRequest
from src.services.event_store import EventStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_event(
    source: str = "copernicus-cdse",
    event_type: EventType = EventType.IMAGERY_ACQUISITION,
    aoi_ids: list[str] | None = None,
    confidence: float | None = 0.9,
    offset_hours: int = 0,
) -> CanonicalEvent:
    ts = datetime(2026, 4, 1, 10 + offset_hours, 0, 0, tzinfo=timezone.utc)
    return CanonicalEvent(
        event_id=make_event_id(source, f"entity_{offset_hours}", ts.isoformat()),
        source=source,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        event_type=event_type,
        event_time=ts,
        ingested_at=ts,
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        centroid={"type": "Point", "coordinates": [0.5, 0.5]},
        attributes={},
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="s3://bucket/test.json"),
        license=LicenseRecord(),
        confidence=confidence,
        correlation_keys=CorrelationKeys(aoi_ids=aoi_ids or []),
    )


@pytest.fixture(autouse=True)
def reset_event_store():
    _store._events.clear()
    yield
    _store._events.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(events_router)
    return TestClient(app)


# ── EventStore unit tests ─────────────────────────────────────────────────────

class TestEventStore:
    def test_ingest_and_get_roundtrip(self):
        store = EventStore()
        event = _make_event()
        store.ingest(event)
        fetched = store.get(event.event_id)
        assert fetched is not None
        assert fetched.event_id == event.event_id

    def test_get_unknown_id_returns_none(self):
        store = EventStore()
        assert store.get("nope") is None

    def test_search_time_filter_excludes_out_of_window(self):
        store = EventStore()
        store.ingest(_make_event(offset_hours=0))   # 10:00
        store.ingest(_make_event(offset_hours=5))   # 15:00 — outside window
        req = EventSearchRequest(
            start_time=datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        result = store.search(req)
        assert result.total == 1

    def test_search_returns_all_within_window(self):
        store = EventStore()
        for i in range(3):
            store.ingest(_make_event(offset_hours=i))
        req = EventSearchRequest(
            start_time=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 1, 14, tzinfo=timezone.utc),
        )
        result = store.search(req)
        assert result.total == 3

    def test_search_filters_by_event_type(self):
        store = EventStore()
        store.ingest(_make_event(event_type=EventType.IMAGERY_ACQUISITION))
        store.ingest(_make_event(event_type=EventType.CHANGE_DETECTION, offset_hours=1))
        req = EventSearchRequest(
            start_time=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 1, 14, tzinfo=timezone.utc),
            event_types=[EventType.CHANGE_DETECTION],
        )
        result = store.search(req)
        assert result.total == 1
        assert result.events[0].event_type == EventType.CHANGE_DETECTION

    def test_search_filters_by_aoi_id(self):
        store = EventStore()
        store.ingest(_make_event(aoi_ids=["aoi_riyadh"]))
        store.ingest(_make_event(aoi_ids=["aoi_dubai"], offset_hours=1))
        req = EventSearchRequest(
            start_time=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 1, 14, tzinfo=timezone.utc),
            aoi_id="aoi_riyadh",
        )
        result = store.search(req)
        assert result.total == 1

    def test_search_min_confidence_filter(self):
        store = EventStore()
        store.ingest(_make_event(confidence=0.3))
        store.ingest(_make_event(confidence=0.9, offset_hours=1))
        req = EventSearchRequest(
            start_time=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 1, 14, tzinfo=timezone.utc),
            min_confidence=0.8,
        )
        result = store.search(req)
        assert result.total == 1
        assert result.events[0].confidence == 0.9

    def test_timeline_buckets_cover_full_window(self):
        store = EventStore()
        for i in range(3):
            store.ingest(_make_event(offset_hours=i))
        tl = store.timeline(
            start_time=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 1, 15, tzinfo=timezone.utc),
            bucket_minutes=60,
        )
        assert tl.total_events == 3
        assert len(tl.buckets) == 6

    def test_active_sources_reflects_ingested_events(self):
        store = EventStore()
        store.ingest(_make_event(source="src-a"))
        store.ingest(_make_event(source="src-b", offset_hours=1))
        sources = store.active_sources()
        connector_ids = [s.connector_id for s in sources]
        assert "src-a" in connector_ids
        assert "src-b" in connector_ids


# ── FastAPI router tests ──────────────────────────────────────────────────────

class TestEventSearchRouter:
    def test_search_endpoint_returns_empty_for_fresh_store(self, client):
        resp = client.post("/api/v1/events/search", json={
            "start_time": "2026-04-01T00:00:00Z",
            "end_time": "2026-04-01T23:59:59Z",
        })
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_get_event_by_id_returns_404_for_unknown(self, client):
        resp = client.get("/api/v1/events/no-such-id")
        assert resp.status_code == 404

    def test_search_invalid_time_range_returns_422(self, client):
        resp = client.post("/api/v1/events/search", json={
            "start_time": "2026-04-02T00:00:00Z",
            "end_time": "2026-04-01T00:00:00Z",  # end before start
        })
        assert resp.status_code == 422

    def test_sources_endpoint_returns_list(self, client):
        resp = client.get("/api/v1/events/sources")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
