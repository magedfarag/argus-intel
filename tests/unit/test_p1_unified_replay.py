"""Phase 1 Track D: Verification tests for the unified replay model.

Validates that imagery, contextual, ship, and aircraft layer events
can all be ingested and replayed from the same EventStore/TelemetryStore.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
)
from src.models.event_search import EventSearchRequest
from src.models.playback import PlaybackQueryRequest
from src.services.event_store import EventStore
from src.services.playback_service import PlaybackService, standard_playback_windows
from src.services.telemetry_store import TelemetryStore

_T0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
_NORM = NormalizationRecord(normalized_by="test")
_PROV = ProvenanceRecord(raw_source_ref="test://unit")
_LIC = LicenseRecord()


def _event(
    eid: str,
    etype: EventType,
    entity_type: EntityType,
    source_type: SourceType,
    t: datetime | None = None,
    lon: float = 56.5,
    lat: float = 26.3,
) -> CanonicalEvent:
    ts = t or _T0
    return CanonicalEvent(
        event_id=eid,
        source="test",
        source_type=source_type,
        entity_type=entity_type,
        event_type=etype,
        event_time=ts,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        centroid={"type": "Point", "coordinates": [lon, lat]},
        attributes={},
        normalization=_NORM,
        provenance=_PROV,
        ingested_at=ts,
        license=_LIC,
    )


# ── Multi-layer replay tests ───────────────────────────────────────────────────


class TestMultiLayerReplay:
    """Validate all key event families replay from the same store."""

    def test_imagery_event_queryable_from_event_store(self) -> None:
        store = EventStore()
        ev = _event(
            "img-1",
            EventType.IMAGERY_ACQUISITION,
            EntityType.IMAGERY_SCENE,
            SourceType.IMAGERY_CATALOG,
        )
        store.ingest(ev)
        assert store.get("img-1") is not None

    def test_contextual_event_queryable_from_event_store(self) -> None:
        store = EventStore()
        ev = _event(
            "ctx-1",
            EventType.CONTEXTUAL_EVENT,
            EntityType.NEWS_ARTICLE,
            SourceType.CONTEXT_FEED,
        )
        store.ingest(ev)
        assert store.get("ctx-1") is not None

    def test_ship_position_queryable_from_telemetry_store(self) -> None:
        ts = TelemetryStore()
        ev = _event(
            "ship-1",
            EventType.SHIP_POSITION,
            EntityType.VESSEL,
            SourceType.TELEMETRY,
        )
        ts.ingest(ev)
        results = ts.query_entity(
            "ship-1",
            _T0 - timedelta(hours=1),
            _T0 + timedelta(hours=1),
        )
        assert len(results) == 1

    def test_aircraft_position_queryable_from_telemetry_store(self) -> None:
        ts = TelemetryStore()
        ev = _event(
            "ac-1",
            EventType.AIRCRAFT_POSITION,
            EntityType.AIRCRAFT,
            SourceType.TELEMETRY,
        )
        ts.ingest(ev)
        results = ts.query_entity(
            "ac-1",
            _T0 - timedelta(hours=1),
            _T0 + timedelta(hours=1),
        )
        assert len(results) == 1

    def test_all_four_layer_types_searchable_via_event_store_search(self) -> None:
        """Imagery, contextual, ship, and aircraft canonical events survive round-trip."""
        store = EventStore()
        layers = [
            _event(
                "img-2",
                EventType.IMAGERY_ACQUISITION,
                EntityType.IMAGERY_SCENE,
                SourceType.IMAGERY_CATALOG,
            ),
            _event(
                "ctx-2",
                EventType.CONTEXTUAL_EVENT,
                EntityType.NEWS_ARTICLE,
                SourceType.CONTEXT_FEED,
            ),
            _event(
                "ship-2",
                EventType.SHIP_POSITION,
                EntityType.VESSEL,
                SourceType.TELEMETRY,
            ),
            _event(
                "ac-2",
                EventType.AIRCRAFT_POSITION,
                EntityType.AIRCRAFT,
                SourceType.TELEMETRY,
            ),
        ]
        store.ingest_batch(layers)
        req = EventSearchRequest(
            start_time=_T0 - timedelta(hours=1),
            end_time=_T0 + timedelta(hours=1),
        )
        resp = store.search(req)
        returned_ids = {e.event_id for e in resp.events}
        assert {"img-2", "ctx-2", "ship-2", "ac-2"}.issubset(returned_ids)

    def test_playback_service_replays_all_four_layers(self) -> None:
        """PlaybackService returns frames for all four event families."""
        store = EventStore()
        layers = [
            _event(
                "img-3",
                EventType.IMAGERY_ACQUISITION,
                EntityType.IMAGERY_SCENE,
                SourceType.IMAGERY_CATALOG,
                t=_T0 + timedelta(hours=0),
            ),
            _event(
                "ctx-3",
                EventType.CONTEXTUAL_EVENT,
                EntityType.NEWS_ARTICLE,
                SourceType.CONTEXT_FEED,
                t=_T0 + timedelta(hours=1),
            ),
            _event(
                "ship-3",
                EventType.SHIP_POSITION,
                EntityType.VESSEL,
                SourceType.TELEMETRY,
                t=_T0 + timedelta(hours=2),
            ),
            _event(
                "ac-3",
                EventType.AIRCRAFT_POSITION,
                EntityType.AIRCRAFT,
                SourceType.TELEMETRY,
                t=_T0 + timedelta(hours=3),
            ),
        ]
        store.ingest_batch(layers)
        svc = PlaybackService(store)
        req = PlaybackQueryRequest(
            start_time=_T0 - timedelta(hours=1),
            end_time=_T0 + timedelta(hours=4),
        )
        resp = svc.query(req)
        frame_ids = {f.event.event_id for f in resp.frames}
        assert {"img-3", "ctx-3", "ship-3", "ac-3"}.issubset(frame_ids)


# ── Late-arrival regression tests ─────────────────────────────────────────────


class TestLateArrivalRegression:
    """Regression tests for late-arrival detection logic."""

    def test_late_arrival_flagged_when_event_time_before_source_max(self) -> None:
        """An event whose event_time < running source max is flagged as late arrival."""
        store = EventStore()
        svc = PlaybackService(store)

        # ev1: ingested first (ingested_at=_T0+1h), event_time=_T0+1h → sets source max
        ev1 = _event(
            "late-1",
            EventType.CONTEXTUAL_EVENT,
            EntityType.NEWS_ARTICLE,
            SourceType.CONTEXT_FEED,
            t=_T0 + timedelta(hours=1),
        )
        # ev2: ingested second (ingested_at=_T0+2h), event_time=_T0 < source max → LATE
        ev2 = _event(
            "late-2",
            EventType.CONTEXTUAL_EVENT,
            EntityType.NEWS_ARTICLE,
            SourceType.CONTEXT_FEED,
            t=_T0,
        ).model_copy(update={"ingested_at": _T0 + timedelta(hours=2)})

        store.ingest_batch([ev1, ev2])

        req = PlaybackQueryRequest(
            start_time=_T0 - timedelta(hours=1),
            end_time=_T0 + timedelta(hours=2),
            include_late_arrivals=True,
        )
        resp = svc.query(req)

        assert resp.late_arrival_count >= 1
        late_frame_ids = {f.event.event_id for f in resp.frames if f.is_late_arrival}
        assert "late-2" in late_frame_ids

    def test_late_arrival_excluded_when_include_flag_false(self) -> None:
        """With include_late_arrivals=False, late frames are stripped from response."""
        store = EventStore()
        svc = PlaybackService(store)

        ev1 = _event(
            "excl-1",
            EventType.CONTEXTUAL_EVENT,
            EntityType.NEWS_ARTICLE,
            SourceType.CONTEXT_FEED,
            t=_T0 + timedelta(hours=1),
        )
        ev2 = _event(
            "excl-2",
            EventType.CONTEXTUAL_EVENT,
            EntityType.NEWS_ARTICLE,
            SourceType.CONTEXT_FEED,
            t=_T0,
        ).model_copy(update={"ingested_at": _T0 + timedelta(hours=2)})
        store.ingest_batch([ev1, ev2])

        req = PlaybackQueryRequest(
            start_time=_T0 - timedelta(hours=1),
            end_time=_T0 + timedelta(hours=2),
            include_late_arrivals=False,
        )
        resp = svc.query(req)

        assert all(not f.is_late_arrival for f in resp.frames)
        assert resp.late_arrival_count == 0

    def test_no_late_arrivals_when_events_arrive_in_chronological_order(self) -> None:
        """Events ingested in ascending event_time order produce no late flags."""
        store = EventStore()
        svc = PlaybackService(store)

        evs = [
            _event(
                f"ord-{i}",
                EventType.IMAGERY_ACQUISITION,
                EntityType.IMAGERY_SCENE,
                SourceType.IMAGERY_CATALOG,
                t=_T0 + timedelta(hours=i),
            )
            for i in range(5)
        ]
        store.ingest_batch(evs)

        req = PlaybackQueryRequest(
            start_time=_T0 - timedelta(hours=1),
            end_time=_T0 + timedelta(hours=6),
        )
        resp = svc.query(req)

        assert resp.late_arrival_count == 0


# ── Standard playback window tests ────────────────────────────────────────────


class TestStandardWindowsDefinition:
    """Validate 24h / 7d / 30d windows are defined and make temporal sense."""

    def test_standard_windows_has_three_entries(self) -> None:
        windows = standard_playback_windows()
        assert set(windows.keys()) == {"24h", "7d", "30d"}

    def test_24h_window_spans_approximately_24_hours(self) -> None:
        windows = standard_playback_windows()
        start, end = windows["24h"]
        delta = end - start
        assert abs(delta.total_seconds() - 86_400) < 5

    def test_7d_window_spans_approximately_7_days(self) -> None:
        windows = standard_playback_windows()
        start, end = windows["7d"]
        delta = end - start
        assert abs(delta.total_seconds() - 7 * 86_400) < 5

    def test_30d_window_spans_approximately_30_days(self) -> None:
        windows = standard_playback_windows()
        start, end = windows["30d"]
        delta = end - start
        assert abs(delta.total_seconds() - 30 * 86_400) < 5

    def test_all_window_end_times_are_utc_aware(self) -> None:
        windows = standard_playback_windows()
        for name, (start, end) in windows.items():
            assert start.tzinfo is not None, f"{name} start is naive"
            assert end.tzinfo is not None, f"{name} end is naive"

    def test_all_windows_end_is_after_start(self) -> None:
        windows = standard_playback_windows()
        for name, (start, end) in windows.items():
            assert end > start, f"{name} window ends before it starts"
