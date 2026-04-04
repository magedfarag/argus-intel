"""Unit tests for the Historical Replay Service (P2-2.8 — ≥10 tests).

Covers:
  - query(): time ordering, source filter, event-type filter, limit
  - Late-arrival detection: quality_flags["late-arrival"], is_late_arrival flag
  - include_late_arrivals=False correctly excludes late frames
  - enqueue_materialize(): job creation, window binning, completed state
  - get_job(): found, not found, job result contents
  - Late-arrival window count aggregation
  - Router endpoint smoke tests via FastAPI TestClient
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.playback import router as playback_router, set_event_store
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
from src.models.playback import MaterializeRequest, PlaybackQueryRequest
from src.services.event_store import EventStore
from src.services.playback_service import PlaybackService


# ── Test helpers ──────────────────────────────────────────────────────────────

_BASE_DT = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)


def _make_event(
    source: str = "src-a",
    event_type: EventType = EventType.IMAGERY_ACQUISITION,
    hours_offset: int = 0,
    aoi_ids: list[str] | None = None,
    ingested_hours_offset: int | None = None,
) -> CanonicalEvent:
    ts = _BASE_DT + timedelta(hours=hours_offset)
    ingested_at = _BASE_DT + timedelta(hours=(ingested_hours_offset if ingested_hours_offset is not None else hours_offset))
    return CanonicalEvent(
        event_id=make_event_id(source, f"e_{source}_{hours_offset}", ts.isoformat()),
        source=source,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        event_type=event_type,
        event_time=ts,
        ingested_at=ingested_at,
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        centroid={"type": "Point", "coordinates": [0.5, 0.5]},
        attributes={},
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="s3://bucket/test.json"),
        license=LicenseRecord(),
        correlation_keys=CorrelationKeys(aoi_ids=aoi_ids or []),
    )


def _store_with(*events: CanonicalEvent) -> EventStore:
    store = EventStore()
    store.ingest_batch(list(events))
    return store


# ── PlaybackService unit tests ────────────────────────────────────────────────


class TestPlaybackServiceQuery:
    def test_empty_store_returns_empty_frames(self):
        svc = PlaybackService(EventStore())
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)
        assert resp.total_frames == 0
        assert resp.frames == []
        assert resp.late_arrival_count == 0

    def test_events_ordered_by_event_time_ascending(self):
        e1 = _make_event(hours_offset=2)
        e0 = _make_event(hours_offset=0)
        e3 = _make_event(hours_offset=3)
        store = _store_with(e1, e0, e3)
        svc = PlaybackService(store)

        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)

        assert resp.total_frames == 3
        times = [f.event.event_time for f in resp.frames]
        assert times == sorted(times)

    def test_sequence_numbers_are_consecutive(self):
        events = [_make_event(hours_offset=i) for i in range(5)]
        svc = PlaybackService(_store_with(*events))
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)
        seqs = [f.sequence for f in resp.frames]
        assert seqs == list(range(1, 6))

    def test_time_filter_excludes_out_of_window(self):
        inside = _make_event(hours_offset=5)
        outside = _make_event(hours_offset=25)
        svc = PlaybackService(_store_with(inside, outside))
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)
        assert resp.total_frames == 1
        assert resp.frames[0].event.event_id == inside.event_id

    def test_source_filter_restricts_results(self):
        e_a = _make_event(source="source-a", hours_offset=1)
        e_b = _make_event(source="source-b", hours_offset=2)
        svc = PlaybackService(_store_with(e_a, e_b))
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
            sources=["source-a"],
        )
        resp = svc.query(req)
        assert resp.total_frames == 1
        assert resp.frames[0].event.source == "source-a"

    def test_event_type_filter_works(self):
        imagery = _make_event(event_type=EventType.IMAGERY_ACQUISITION, hours_offset=1)
        contextual = _make_event(event_type=EventType.CONTEXTUAL_EVENT, hours_offset=2)
        svc = PlaybackService(_store_with(imagery, contextual))
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
            event_types=[EventType.CONTEXTUAL_EVENT],
        )
        resp = svc.query(req)
        assert resp.total_frames == 1
        assert resp.frames[0].event.event_type == EventType.CONTEXTUAL_EVENT

    def test_limit_caps_results(self):
        events = [_make_event(hours_offset=i) for i in range(10)]
        svc = PlaybackService(_store_with(*events))
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
            limit=3,
        )
        resp = svc.query(req)
        assert resp.total_frames <= 3

    def test_sources_included_list(self):
        e_a = _make_event(source="src-alpha", hours_offset=1)
        e_b = _make_event(source="src-beta", hours_offset=2)
        svc = PlaybackService(_store_with(e_a, e_b))
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)
        assert "src-alpha" in resp.sources_included
        assert "src-beta" in resp.sources_included


class TestLateArrivalDetection:
    """P2-2.7: late-arriving events are flagged."""

    def _build_late_store(self) -> EventStore:
        """Insert events so that e_old arrives after e_new (simulates late-delivery).

        event_time order: e_old (hour 1) → e_new (hour 5)
        But ingested_at order: e_new ingested first (hour 5), e_old ingested later (hour 7).
        """
        e_new = _make_event(source="src", hours_offset=5, ingested_hours_offset=5)
        e_old = _make_event(source="src", hours_offset=1, ingested_hours_offset=7)
        store = EventStore()
        # Ingest e_new first so source max is established at hour 5
        store.ingest(e_new)
        store.ingest(e_old)
        return store

    def test_late_arrival_flag_set_on_event(self):
        store = self._build_late_store()
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)
        late_frames = [f for f in resp.frames if f.is_late_arrival]
        assert len(late_frames) == 1
        assert "late-arrival" in late_frames[0].event.quality_flags

    def test_late_arrival_count_in_response(self):
        store = self._build_late_store()
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
        )
        resp = svc.query(req)
        assert resp.late_arrival_count == 1

    def test_exclude_late_arrivals_filters_them_out(self):
        store = self._build_late_store()
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=24),
            include_late_arrivals=False,
        )
        resp = svc.query(req)
        assert resp.late_arrival_count == 0
        assert all(not f.is_late_arrival for f in resp.frames)


class TestMaterializeAndJobs:
    def test_materialize_returns_job_id(self):
        svc = PlaybackService(EventStore())
        req = MaterializeRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=4),
            window_size_minutes=60,
        )
        resp = svc.enqueue_materialize(req)
        assert resp.job_id
        assert resp.status == "completed"

    def test_get_job_returns_status(self):
        svc = PlaybackService(EventStore())
        req = MaterializeRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=4),
            window_size_minutes=60,
        )
        mat_resp = svc.enqueue_materialize(req)
        job = svc.get_job(mat_resp.job_id)
        assert job is not None
        assert job.job_id == mat_resp.job_id
        assert job.state == "completed"

    def test_get_job_unknown_id_returns_none(self):
        svc = PlaybackService(EventStore())
        assert svc.get_job("does-not-exist") is None

    def test_materialize_windows_cover_full_range(self):
        svc = PlaybackService(EventStore())
        req = MaterializeRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=4),
            window_size_minutes=60,
        )
        mat_resp = svc.enqueue_materialize(req)
        job = svc.get_job(mat_resp.job_id)
        assert job is not None
        assert job.total_windows == 4  # 4 × 60min windows

    def test_materialize_window_event_binning(self):
        e_h1 = _make_event(hours_offset=1)
        e_h3 = _make_event(hours_offset=3)
        svc = PlaybackService(_store_with(e_h1, e_h3))
        req = MaterializeRequest(
            start_time=_BASE_DT,
            end_time=_BASE_DT + timedelta(hours=4),
            window_size_minutes=60,
        )
        mat_resp = svc.enqueue_materialize(req)
        job = svc.get_job(mat_resp.job_id)
        assert job is not None
        assert job.total_events == 2
        non_empty = [w for w in job.windows if w.event_count > 0]
        assert len(non_empty) == 2


# ── Router endpoint smoke tests ───────────────────────────────────────────────


@pytest.fixture
def playback_client():
    store = EventStore()
    store.ingest(_make_event(hours_offset=2))
    store.ingest(_make_event(hours_offset=4))
    set_event_store(store)
    app = FastAPI()
    app.include_router(playback_router)
    return TestClient(app)


class TestPlaybackRouterEndpoints:
    def test_query_endpoint_200(self, playback_client: TestClient):
        resp = playback_client.post(
            "/api/v1/playback/query",
            json={
                "start_time": "2026-04-01T00:00:00Z",
                "end_time": "2026-04-01T23:59:00Z",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "frames" in body
        assert body["total_frames"] == 2

    def test_query_endpoint_422_reversed_window(self, playback_client: TestClient):
        resp = playback_client.post(
            "/api/v1/playback/query",
            json={
                "start_time": "2026-04-01T23:00:00Z",
                "end_time": "2026-04-01T00:00:00Z",
            },
        )
        assert resp.status_code == 422

    def test_materialize_endpoint_202(self, playback_client: TestClient):
        resp = playback_client.post(
            "/api/v1/playback/materialize",
            json={
                "start_time": "2026-04-01T00:00:00Z",
                "end_time": "2026-04-01T12:00:00Z",
                "window_size_minutes": 60,
            },
        )
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    def test_get_job_endpoint_success(self, playback_client: TestClient):
        mat_resp = playback_client.post(
            "/api/v1/playback/materialize",
            json={
                "start_time": "2026-04-01T00:00:00Z",
                "end_time": "2026-04-01T06:00:00Z",
                "window_size_minutes": 60,
            },
        )
        job_id = mat_resp.json()["job_id"]
        resp = playback_client.get(f"/api/v1/playback/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["state"] == "completed"

    def test_get_job_endpoint_404_unknown(self, playback_client: TestClient):
        resp = playback_client.get("/api/v1/playback/jobs/nonexistent-job")
        assert resp.status_code == 404


# ── Unified write→read path integration tests (Track C) ──────────────────────


class TestUnifiedQueryPath:
    """Verify that pollers writing to the singleton are visible via PlaybackService."""

    def test_event_ingested_via_default_store_is_visible_in_playback_query(self):
        """Events written to the default singleton are readable via PlaybackService(singleton)."""
        import src.services.event_store as _es_mod

        original = _es_mod._default_store
        try:
            fresh_store = EventStore()
            _es_mod._default_store = fresh_store

            from src.services.event_store import get_default_event_store

            # Simulate poller writing an event to the process-wide singleton
            event = _make_event(source="ais-poller", hours_offset=2)
            get_default_event_store().ingest(event)

            # PlaybackService created from the same singleton must see the event
            svc = PlaybackService(get_default_event_store())
            req = PlaybackQueryRequest(
                start_time=_BASE_DT,
                end_time=_BASE_DT + timedelta(hours=24),
            )
            resp = svc.query(req)
            assert resp.total_frames == 1
            assert resp.frames[0].event.event_id == event.event_id
        finally:
            _es_mod._default_store = original

    def test_telemetry_ingested_via_default_store_is_visible_in_entity_track(self):
        """Ship positions written to the default telemetry singleton are readable via query_entity."""
        import src.services.telemetry_store as _ts_mod
        from src.services.telemetry_store import TelemetryStore, get_default_telemetry_store

        original = _ts_mod._default_store
        try:
            _ts_mod._default_store = TelemetryStore()

            entity_id = "vessel-mmsi-123456789"
            ts = _BASE_DT + timedelta(hours=1)
            ship_event = CanonicalEvent(
                event_id=make_event_id("ais-live", entity_id, ts.isoformat()),
                source="ais-live",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.VESSEL,
                event_type=EventType.SHIP_POSITION,
                event_time=ts,
                ingested_at=ts,
                entity_id=entity_id,
                geometry={"type": "Point", "coordinates": [55.0, 25.0]},
                centroid={"type": "Point", "coordinates": [55.0, 25.0]},
                attributes={},
                normalization=NormalizationRecord(normalized_by="ais-connector"),
                provenance=ProvenanceRecord(raw_source_ref="ais://raw/mmsi/123456789"),
                license=LicenseRecord(),
                correlation_keys=CorrelationKeys(),
            )
            # Simulate AIS poller writing to the singleton
            get_default_telemetry_store().ingest(ship_event)

            # Entity track query via the same singleton
            positions = get_default_telemetry_store().query_entity(
                entity_id,
                _BASE_DT,
                _BASE_DT + timedelta(hours=24),
            )
            assert len(positions) == 1
            assert positions[0].entity_id == entity_id
            assert positions[0].event_type == EventType.SHIP_POSITION
        finally:
            _ts_mod._default_store = original

    def test_standard_playback_windows_returns_three_windows(self):
        """standard_playback_windows() returns exactly the 24h, 7d, 30d keys with correct spans."""
        from src.services.playback_service import standard_playback_windows

        windows = standard_playback_windows()
        assert set(windows.keys()) == {"24h", "7d", "30d"}

        start_24h, end_24h = windows["24h"]
        assert abs((end_24h - start_24h).total_seconds() - 24 * 3600) < 2

        start_7d, end_7d = windows["7d"]
        assert abs((end_7d - start_7d).total_seconds() - 7 * 24 * 3600) < 2

        start_30d, end_30d = windows["30d"]
        assert abs((end_30d - start_30d).total_seconds() - 30 * 24 * 3600) < 2
