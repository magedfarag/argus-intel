"""P1-6.3: Timeline filter correctness validation on reference pilot AOIs.

Verifies that:
- Events strictly inside the time window are returned.
- Events outside the time window are excluded.
- Source-type filter selects the correct event families.
- Results are ordered by event_time ascending.
- Boundary conditions at start/end of window.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
)
from src.models.pilot_aois import PILOT_AOIS
from src.services.event_store import EventStore
from src.services.playback_service import PlaybackService
from src.models.playback import PlaybackQueryRequest


def _utc(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


def _make_event(
    source: str = "gdelt",
    source_type: SourceType = SourceType.CONTEXT_FEED,
    event_type: EventType = EventType.CONTEXTUAL_EVENT,
    entity_type: EntityType = EntityType.NEWS_ARTICLE,
    event_time: str = "2026-01-15T12:00:00",
    lat: float = 24.80,
    lon: float = 46.67,
    event_id: str | None = None,
) -> CanonicalEvent:
    eid = event_id or f"{source}-{event_time}-{lat}-{lon}"
    pt = {"type": "Point", "coordinates": [lon, lat]}
    return CanonicalEvent(
        event_id=eid,
        event_time=_utc(event_time),
        ingested_at=_utc(event_time),
        source=source,
        source_type=source_type,
        entity_type=entity_type,
        event_type=event_type,
        geometry=pt,
        centroid=pt,
        confidence=0.7,
        quality_flags=[],
        normalization=NormalizationRecord(normalized_by="test.fixture"),
        provenance=ProvenanceRecord(raw_source_ref="test://fixture"),
    )


@pytest.fixture()
def store_with_events() -> EventStore:
    store = EventStore()
    store.ingest(_make_event(event_time="2026-01-10T00:00:00", event_id="before"))
    store.ingest(_make_event(event_time="2026-01-15T12:00:00", event_id="inside-1"))
    store.ingest(_make_event(event_time="2026-01-16T08:00:00", event_id="inside-2"))
    store.ingest(_make_event(event_time="2026-01-22T00:00:00", event_id="after"))
    return store


@pytest.fixture()
def svc(store_with_events: EventStore) -> PlaybackService:
    return PlaybackService(store_with_events)


class TestTimelineWindowFilter:
    """P1-6.3: Verify that only events within [start, end] are returned."""

    def test_events_inside_window_returned(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-14T00:00:00"),
            end_time=_utc("2026-01-20T00:00:00"),
        )
        resp = svc.query(req)
        times = [f.event.event_time for f in resp.frames]
        assert all(
            _utc("2026-01-14T00:00:00") <= t <= _utc("2026-01-20T00:00:00")
            for t in times
        )

    def test_events_before_window_excluded(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-14T00:00:00"),
            end_time=_utc("2026-01-20T00:00:00"),
        )
        resp = svc.query(req)
        event_ids = [f.event.event_id for f in resp.frames]
        assert "before" not in event_ids

    def test_events_after_window_excluded(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-14T00:00:00"),
            end_time=_utc("2026-01-20T00:00:00"),
        )
        resp = svc.query(req)
        event_ids = [f.event.event_id for f in resp.frames]
        assert "after" not in event_ids

    def test_frames_ordered_by_event_time(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-10T00:00:00"),
            end_time=_utc("2026-01-22T23:59:59"),
        )
        resp = svc.query(req)
        times = [f.event.event_time for f in resp.frames]
        assert times == sorted(times)

    def test_empty_window_returns_no_frames(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2025-01-01T00:00:00"),
            end_time=_utc("2025-01-02T00:00:00"),
        )
        resp = svc.query(req)
        assert resp.frames == []
        assert resp.total_frames == 0

    def test_source_type_filter_context_only(self) -> None:
        store = EventStore()
        store.ingest(_make_event(source="gdelt", source_type=SourceType.CONTEXT_FEED, event_time="2026-01-15T00:00:00", event_id="ctx-1"))
        store.ingest(_make_event(source="sentinel2", source_type=SourceType.IMAGERY_CATALOG, event_type=EventType.IMAGERY_ACQUISITION, entity_type=EntityType.IMAGERY_SCENE, event_time="2026-01-15T01:00:00", event_id="img-1"))
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-14T00:00:00"),
            end_time=_utc("2026-01-16T00:00:00"),
            source_types=[SourceType.CONTEXT_FEED],
        )
        resp = svc.query(req)
        assert all(f.event.source_type == SourceType.CONTEXT_FEED for f in resp.frames)

    def test_source_type_filter_imagery_only(self) -> None:
        store = EventStore()
        store.ingest(_make_event(source="gdelt", source_type=SourceType.CONTEXT_FEED, event_time="2026-01-15T00:00:00", event_id="ctx-2"))
        store.ingest(_make_event(source="sentinel2", source_type=SourceType.IMAGERY_CATALOG, event_type=EventType.IMAGERY_ACQUISITION, entity_type=EntityType.IMAGERY_SCENE, event_time="2026-01-15T01:00:00", event_id="img-2"))
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-14T00:00:00"),
            end_time=_utc("2026-01-16T00:00:00"),
            source_types=[SourceType.IMAGERY_CATALOG],
        )
        resp = svc.query(req)
        assert all(f.event.source_type == SourceType.IMAGERY_CATALOG for f in resp.frames)

    def test_limit_parameter_respected(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-01T00:00:00"),
            end_time=_utc("2026-02-01T00:00:00"),
            limit=1,
        )
        resp = svc.query(req)
        assert len(resp.frames) <= 1

    def test_sources_included_reflects_returned_events(self, svc: PlaybackService) -> None:
        req = PlaybackQueryRequest(
            start_time=_utc("2026-01-01T00:00:00"),
            end_time=_utc("2026-02-01T00:00:00"),
        )
        resp = svc.query(req)
        returned_sources = {f.event.source for f in resp.frames}
        assert returned_sources == set(resp.sources_included)

    def test_late_arrival_count_matches_flags(self) -> None:
        store = EventStore()
        # Ingest in out-of-order ingested_at sequence to trigger late-arrival
        e1 = _make_event(event_time="2026-02-15T10:00:00", event_id="late-e1")
        e2 = _make_event(event_time="2026-02-15T08:00:00", event_id="late-e2")
        # Ingest e1 first (later event_time), then e2 (earlier event_time but ingested after)
        e1 = e1.model_copy(update={"ingested_at": _utc("2026-02-15T10:05:00")})
        e2 = e2.model_copy(update={"ingested_at": _utc("2026-02-15T10:10:00")})  # ingested after e1 but event_time earlier
        store.ingest(e1)
        store.ingest(e2)
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc("2026-02-14T00:00:00"),
            end_time=_utc("2026-02-16T00:00:00"),
            include_late_arrivals=True,
        )
        resp = svc.query(req)
        late_flag_count = sum(1 for f in resp.frames if f.is_late_arrival)
        assert late_flag_count == resp.late_arrival_count


class TestPilotAoiGeometry:
    """P1-6.3: Pilot AOI reference geometries are valid and correctly bounded."""

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_aoi_has_required_fields(self, aoi: dict) -> None:
        assert "id" in aoi
        assert "name" in aoi
        assert "geometry" in aoi
        assert "centroid" in aoi

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_centroid_within_polygon_bbox(self, aoi: dict) -> None:
        coords = aoi["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        c = aoi["centroid"]
        assert min(lons) <= c["lon"] <= max(lons)
        assert min(lats) <= c["lat"] <= max(lats)

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_geometry_ring_is_closed(self, aoi: dict) -> None:
        coords = aoi["geometry"]["coordinates"][0]
        assert coords[0] == coords[-1], "Polygon ring must be closed"

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_coordinates_in_wgs84_range(self, aoi: dict) -> None:
        for coord in aoi["geometry"]["coordinates"][0]:
            assert -180 <= coord[0] <= 180, f"Longitude out of range: {coord[0]}"
            assert -90 <= coord[1] <= 90, f"Latitude out of range: {coord[1]}"

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_expected_stac_collections_present(self, aoi: dict) -> None:
        assert len(aoi["expected_stac_collections"]) >= 1

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_construction_activity_field(self, aoi: dict) -> None:
        assert aoi.get("construction_activity") in {"low", "medium", "high"}


class TestTimelineEdgeCases:
    """P1-6.3: Boundary and edge-case timeline filter behaviour."""

    def test_single_event_exactly_at_start_boundary(self) -> None:
        store = EventStore()
        ts = "2026-03-01T00:00:00"
        store.ingest(_make_event(event_time=ts, event_id="boundary-start"))
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc(ts),
            end_time=_utc("2026-03-02T00:00:00"),
        )
        resp = svc.query(req)
        assert len(resp.frames) == 1

    def test_single_event_exactly_at_end_boundary(self) -> None:
        store = EventStore()
        ts = "2026-03-02T00:00:00"
        store.ingest(_make_event(event_time=ts, event_id="boundary-end"))
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc("2026-03-01T00:00:00"),
            end_time=_utc(ts),
        )
        resp = svc.query(req)
        assert len(resp.frames) == 1

    def test_multiple_events_same_timestamp(self) -> None:
        """Multiple events with the same event_time are all returned."""
        store = EventStore()
        ts = "2026-03-15T12:00:00"
        for i in range(3):
            store.ingest(_make_event(event_time=ts, event_id=f"multi-same-ts-{i}"))
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc("2026-03-14T00:00:00"),
            end_time=_utc("2026-03-16T00:00:00"),
        )
        resp = svc.query(req)
        assert len(resp.frames) == 3

    def test_sequence_numbers_are_unique(self) -> None:
        store = EventStore()
        for i in range(5):
            store.ingest(_make_event(event_time=f"2026-04-0{i+1}T00:00:00", event_id=f"seq-{i}"))
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_utc("2026-04-01T00:00:00"),
            end_time=_utc("2026-04-10T00:00:00"),
        )
        resp = svc.query(req)
        seqs = [f.sequence for f in resp.frames]
        assert len(seqs) == len(set(seqs))
