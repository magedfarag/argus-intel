"""Tests for TelemetryStore — P3-1.6, P3-4.1–P3-4.4.

Covers:
- Ingestion + duplicate suppression (P3-4.4)
- Non-position event type rejection
- query_entity: time windowing + uniform subsampling
- query_viewport: bbox spatial filter + max_events cap (P3-3.5)
- get_entity_ids: source/type filtering
- enforce_retention: age cutoff + count cap (P3-4.1)
- thin_old_positions: downsampling for old data (P3-4.2)
- get_ingest_lag_stats: median/p95 lag (P3-4.3)
- Late-arrival handling (P3-4.4)
- Thread-safety: concurrent ingest + query
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import patch

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
    make_event_id,
)
from src.services.telemetry_store import (
    IngestLagStats,
    RetentionPolicy,
    TelemetryStore,
    _extract_point_coords,
    _uniform_subsample,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

_BASE_TIME = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_ship(
    mmsi: str,
    lon: float,
    lat: float,
    *,
    offset_minutes: int = 0,
    lag_seconds: float = 5.0,
) -> CanonicalEvent:
    event_time = _BASE_TIME + timedelta(minutes=offset_minutes)
    ingested_at = event_time + timedelta(seconds=lag_seconds)
    return CanonicalEvent(
        event_id=make_event_id("ais-stream", mmsi, event_time.isoformat()),
        source="ais-stream",
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.VESSEL,
        entity_id=mmsi,
        event_type=EventType.SHIP_POSITION,
        event_time=event_time,
        ingested_at=ingested_at,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        centroid={"type": "Point", "coordinates": [lon, lat]},
        normalization=NormalizationRecord(normalized_by="ais-stream"),
        provenance=ProvenanceRecord(raw_source_ref="ws://aisstream.io"),
        license=LicenseRecord(),
        correlation_keys=CorrelationKeys(mmsi=mmsi),
        attributes={"mmsi": mmsi, "speed_kn": 5.0},
    )


def _make_aircraft(
    icao24: str,
    lon: float,
    lat: float,
    *,
    offset_minutes: int = 0,
    lag_seconds: float = 10.0,
) -> CanonicalEvent:
    event_time = _BASE_TIME + timedelta(minutes=offset_minutes)
    ingested_at = event_time + timedelta(seconds=lag_seconds)
    return CanonicalEvent(
        event_id=make_event_id("opensky", icao24, event_time.isoformat()),
        source="opensky",
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.AIRCRAFT,
        entity_id=icao24,
        event_type=EventType.AIRCRAFT_POSITION,
        event_time=event_time,
        ingested_at=ingested_at,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        centroid={"type": "Point", "coordinates": [lon, lat]},
        normalization=NormalizationRecord(normalized_by="opensky"),
        provenance=ProvenanceRecord(raw_source_ref="https://opensky.example"),
        license=LicenseRecord(commercial_use="not-allowed"),
        correlation_keys=CorrelationKeys(icao24=icao24),
        attributes={"icao24": icao24, "altitude_m": 9500.0},
    )


def _make_imagery(lon: float, lat: float) -> CanonicalEvent:
    """Non-position event — should be rejected by TelemetryStore."""
    return CanonicalEvent(
        event_id=make_event_id("earth-search", "scene-001", _BASE_TIME.isoformat()),
        source="earth-search",
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        event_type=EventType.IMAGERY_ACQUISITION,
        event_time=_BASE_TIME,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        centroid={"type": "Point", "coordinates": [lon, lat]},
        normalization=NormalizationRecord(normalized_by="earth-search"),
        provenance=ProvenanceRecord(raw_source_ref="stac://"),
        license=LicenseRecord(),
    )


# ── Helper unit tests ─────────────────────────────────────────────────────────


class TestExtractPointCoords:
    def test_point(self) -> None:
        lon, lat = _extract_point_coords({"type": "Point", "coordinates": [55.3, 25.2]})
        assert lon == pytest.approx(55.3)
        assert lat == pytest.approx(25.2)

    def test_polygon_centroid(self) -> None:
        ring = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]
        lon, lat = _extract_point_coords({"type": "Polygon", "coordinates": [ring]})
        assert lon == pytest.approx(1.0)
        assert lat == pytest.approx(1.0)

    def test_linestring_first_point(self) -> None:
        lon, lat = _extract_point_coords(
            {"type": "LineString", "coordinates": [[10.0, 20.0], [11.0, 21.0]]}
        )
        assert lon == pytest.approx(10.0)
        assert lat == pytest.approx(20.0)

    def test_unknown_type_returns_none(self) -> None:
        lon, lat = _extract_point_coords({"type": "Unknown", "coordinates": []})
        assert lon is None and lat is None

    def test_empty_coordinates_returns_none(self) -> None:
        lon, lat = _extract_point_coords({"type": "Point", "coordinates": []})
        assert lon is None and lat is None


class TestUniformSubsample:
    def test_no_reduction_needed(self) -> None:
        events = [_make_ship("123", 0.0, 0.0, offset_minutes=i) for i in range(5)]
        result = _uniform_subsample(events, 10)
        assert len(result) == 5

    def test_first_and_last_preserved(self) -> None:
        events = [_make_ship("123", 0.0, 0.0, offset_minutes=i) for i in range(20)]
        result = _uniform_subsample(events, 5)
        assert result[0].event_id == events[0].event_id
        assert result[-1].event_id == events[-1].event_id

    def test_correct_count(self) -> None:
        events = [_make_ship("123", 0.0, 0.0, offset_minutes=i) for i in range(100)]
        result = _uniform_subsample(events, 10)
        assert len(result) == 10

    def test_n_equals_one(self) -> None:
        events = [_make_ship("123", 0.0, 0.0, offset_minutes=i) for i in range(5)]
        result = _uniform_subsample(events, 1)
        assert len(result) == 1
        assert result[0].event_id == events[0].event_id


# ── TelemetryStore: ingestion ─────────────────────────────────────────────────


class TestTelemetryStoreIngest:
    def test_ingest_ship_position_accepted(self) -> None:
        store = TelemetryStore()
        ship = _make_ship("123456789", 55.3, 25.2)
        assert store.ingest(ship) is True
        assert store.count() == 1

    def test_ingest_aircraft_position_accepted(self) -> None:
        store = TelemetryStore()
        ac = _make_aircraft("abc123", 55.3, 25.2)
        assert store.ingest(ac) is True
        assert store.count() == 1

    def test_ingest_non_position_rejected(self) -> None:
        store = TelemetryStore()
        img = _make_imagery(55.3, 25.2)
        assert store.ingest(img) is False
        assert store.count() == 0

    def test_duplicate_event_id_ignored(self) -> None:
        store = TelemetryStore()
        ship = _make_ship("999", 55.3, 25.2)
        store.ingest(ship)
        result = store.ingest(ship)
        assert result is False
        assert store.count() == 1

    def test_ingest_batch_returns_accepted_count(self) -> None:
        store = TelemetryStore()
        ships = [_make_ship("111", 55.0 + i * 0.1, 25.0, offset_minutes=i) for i in range(5)]
        img = _make_imagery(55.3, 25.2)
        count = store.ingest_batch(ships + [img])
        assert count == 5
        assert store.count() == 5

    def test_ingest_batch_deduplicates(self) -> None:
        store = TelemetryStore()
        ship = _make_ship("777", 55.3, 25.2)
        count = store.ingest_batch([ship, ship, ship])
        assert count == 1
        assert store.count() == 1


# ── TelemetryStore: queries ───────────────────────────────────────────────────


class TestTelemetryStoreQueryEntity:
    def test_returns_positions_in_window(self) -> None:
        store = TelemetryStore()
        for i in range(10):
            store.ingest(_make_ship("MMSI001", 55.0, 25.0, offset_minutes=i * 10))
        start = _BASE_TIME
        end = _BASE_TIME + timedelta(minutes=50)
        results = store.query_entity("MMSI001", start, end)
        assert all(start <= e.event_time <= end for e in results)
        assert len(results) == 6  # offsets 0, 10, 20, 30, 40, 50

    def test_returns_empty_for_unknown_entity(self) -> None:
        store = TelemetryStore()
        results = store.query_entity("UNKNOWN", _BASE_TIME, _BASE_TIME + timedelta(hours=1))
        assert results == []

    def test_max_points_subsample_preserves_endpoints(self) -> None:
        store = TelemetryStore()
        for i in range(100):
            store.ingest(_make_ship("MMSI002", 55.0 + i * 0.001, 25.0, offset_minutes=i))
        results = store.query_entity(
            "MMSI002",
            _BASE_TIME,
            _BASE_TIME + timedelta(hours=2),
            max_points=10,
        )
        assert len(results) == 10
        assert results[0].event_time == _BASE_TIME
        assert results[-1].event_time == _BASE_TIME + timedelta(minutes=99)

    def test_results_sorted_by_event_time_ascending(self) -> None:
        store = TelemetryStore()
        for i in [5, 2, 8, 1, 4]:
            store.ingest(_make_ship("MMSI003", 55.0, 25.0, offset_minutes=i))
        results = store.query_entity("MMSI003", _BASE_TIME, _BASE_TIME + timedelta(hours=1))
        times = [e.event_time for e in results]
        assert times == sorted(times)


class TestTelemetryStoreQueryViewport:
    def test_filters_by_bbox(self) -> None:
        store = TelemetryStore()
        # Dubai area
        store.ingest(_make_ship("SHIP_A", 55.3, 25.2))
        # Outside bbox
        store.ingest(_make_ship("SHIP_B", 46.6, 24.8, offset_minutes=1))
        bbox = (55.0, 25.0, 55.6, 25.5)  # (west, south, east, north)
        results = store.query_viewport(
            bbox,
            _BASE_TIME - timedelta(minutes=1),
            _BASE_TIME + timedelta(hours=1),
        )
        assert len(results) == 1
        assert results[0].entity_id == "SHIP_A"

    def test_max_events_cap(self) -> None:
        store = TelemetryStore()
        for i in range(50):
            store.ingest(_make_ship(f"S{i:03d}", 55.0 + i * 0.001, 25.0, offset_minutes=i))
        bbox = (54.0, 24.0, 56.0, 26.0)
        results = store.query_viewport(
            bbox,
            _BASE_TIME - timedelta(minutes=1),
            _BASE_TIME + timedelta(hours=2),
            max_events=10,
        )
        assert len(results) == 10

    def test_sources_filter(self) -> None:
        store = TelemetryStore()
        store.ingest(_make_ship("S1", 55.3, 25.2))
        store.ingest(_make_aircraft("AC1", 55.3, 25.25, offset_minutes=1))
        bbox = (55.0, 25.0, 55.6, 25.5)
        results = store.query_viewport(
            bbox,
            _BASE_TIME - timedelta(minutes=1),
            _BASE_TIME + timedelta(hours=1),
            sources=["opensky"],
        )
        assert len(results) == 1
        assert results[0].source == "opensky"

    def test_sorted_newest_first(self) -> None:
        store = TelemetryStore()
        for i in range(5):
            store.ingest(_make_ship(f"S{i}", 55.3, 25.2, offset_minutes=i * 10))
        bbox = (55.0, 25.0, 55.6, 25.5)
        results = store.query_viewport(
            bbox,
            _BASE_TIME - timedelta(minutes=1),
            _BASE_TIME + timedelta(hours=1),
        )
        times = [e.event_time for e in results]
        assert times == sorted(times, reverse=True)


# ── Retention enforcement (P3-4.1) ───────────────────────────────────────────


class TestEnforceRetention:
    def test_prunes_old_events(self) -> None:
        store = TelemetryStore()
        now = datetime.now(timezone.utc)
        old_t = now - timedelta(days=60)   # 60 days ago — beyond any 30-day policy
        recent_t = now - timedelta(hours=1)  # 1 hour ago — definitely within 30 days
        from src.models.canonical_event import make_event_id as _mid
        old = CanonicalEvent(
            event_id=_mid("ais-stream", "M1", old_t.isoformat()),
            source="ais-stream",
            source_type=SourceType.TELEMETRY,
            entity_type=EntityType.VESSEL,
            entity_id="M1",
            event_type=EventType.SHIP_POSITION,
            event_time=old_t,
            ingested_at=old_t + timedelta(seconds=5),
            geometry={"type": "Point", "coordinates": [55.3, 25.2]},
            centroid={"type": "Point", "coordinates": [55.3, 25.2]},
            normalization=NormalizationRecord(normalized_by="ais-stream"),
            provenance=ProvenanceRecord(raw_source_ref="ws://"),
            license=LicenseRecord(),
        )
        recent = CanonicalEvent(
            event_id=_mid("ais-stream", "M1", recent_t.isoformat()),
            source="ais-stream",
            source_type=SourceType.TELEMETRY,
            entity_type=EntityType.VESSEL,
            entity_id="M1",
            event_type=EventType.SHIP_POSITION,
            event_time=recent_t,
            ingested_at=recent_t + timedelta(seconds=5),
            geometry={"type": "Point", "coordinates": [55.3, 25.2]},
            centroid={"type": "Point", "coordinates": [55.3, 25.2]},
            normalization=NormalizationRecord(normalized_by="ais-stream"),
            provenance=ProvenanceRecord(raw_source_ref="ws://"),
            license=LicenseRecord(),
        )
        store.ingest(old)
        store.ingest(recent)
        policy = RetentionPolicy(max_age_days=30)
        pruned = store.enforce_retention(policy)
        assert pruned == 1
        assert store.count() == 1

    def test_count_cap_keeps_newest(self) -> None:
        store = TelemetryStore()
        now = datetime.now(timezone.utc)
        # 20 recent events (within last hour)
        for i in range(20):
            t = now - timedelta(minutes=20 - i)  # oldest at i=0, newest at i=19
            ev = CanonicalEvent(
                event_id=make_event_id("ais-stream", "M2", t.isoformat()),
                source="ais-stream",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.VESSEL,
                entity_id="M2",
                event_type=EventType.SHIP_POSITION,
                event_time=t,
                ingested_at=t + timedelta(seconds=5),
                geometry={"type": "Point", "coordinates": [55.3, 25.2]},
                centroid={"type": "Point", "coordinates": [55.3, 25.2]},
                normalization=NormalizationRecord(normalized_by="ais-stream"),
                provenance=ProvenanceRecord(raw_source_ref="ws://"),
                license=LicenseRecord(),
            )
            store.ingest(ev)
        policy = RetentionPolicy(max_age_days=365, max_events_per_entity=10)
        pruned = store.enforce_retention(policy)
        assert pruned == 10
        assert store.count() == 10
        # Newest 10 should remain (i=10..19)
        results = store.query_entity("M2", now - timedelta(hours=1), now + timedelta(minutes=1))
        times = [e.event_time for e in results]
        assert len(times) == 10
        assert min(times) >= now - timedelta(minutes=10, seconds=30)

    def test_no_pruning_within_policy(self) -> None:
        store = TelemetryStore()
        for i in range(5):
            store.ingest(_make_ship("M3", 55.3, 25.2, offset_minutes=i))
        policy = RetentionPolicy(max_age_days=365, max_events_per_entity=1000)
        pruned = store.enforce_retention(policy)
        assert pruned == 0
        assert store.count() == 5


# ── Position thinning (P3-4.2) ────────────────────────────────────────────────


class TestThinOldPositions:
    def test_recent_events_not_thinned(self) -> None:
        store = TelemetryStore()
        now = datetime.now(timezone.utc)
        # 10 events within the last 2 hours — well within thin_after_age_days=7
        for i in range(10):
            t = now - timedelta(minutes=20 - i * 2)  # all within last 20 minutes
            ev = CanonicalEvent(
                event_id=make_event_id("ais-stream", "T1", t.isoformat()),
                source="ais-stream",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.VESSEL,
                entity_id="T1",
                event_type=EventType.SHIP_POSITION,
                event_time=t,
                ingested_at=t + timedelta(seconds=5),
                geometry={"type": "Point", "coordinates": [55.3, 25.2]},
                centroid={"type": "Point", "coordinates": [55.3, 25.2]},
                normalization=NormalizationRecord(normalized_by="ais-stream"),
                provenance=ProvenanceRecord(raw_source_ref="ws://"),
                license=LicenseRecord(),
            )
            store.ingest(ev)
        policy = RetentionPolicy(thin_after_age_days=7, thin_interval_seconds=300)
        thinned = store.thin_old_positions(policy)
        assert thinned == 0
        assert store.count() == 10

    def test_old_events_thinned_by_interval(self) -> None:
        store = TelemetryStore()
        old_base = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
        # 20 old events, 1 minute apart → with 5-min interval, keep ~4-5
        for i in range(20):
            t = old_base + timedelta(minutes=i)
            ev = CanonicalEvent(
                event_id=make_event_id("ais-stream", "T2", t.isoformat()),
                source="ais-stream",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.VESSEL,
                entity_id="T2",
                event_type=EventType.SHIP_POSITION,
                event_time=t,
                ingested_at=t + timedelta(seconds=5),
                geometry={"type": "Point", "coordinates": [55.3, 25.2]},
                centroid={"type": "Point", "coordinates": [55.3, 25.2]},
                normalization=NormalizationRecord(normalized_by="ais-stream"),
                provenance=ProvenanceRecord(raw_source_ref="ws://"),
                license=LicenseRecord(),
            )
            store.ingest(ev)

        policy = RetentionPolicy(thin_after_age_days=7, thin_interval_seconds=300)
        thinned = store.thin_old_positions(policy)
        assert thinned > 0
        assert store.count() < 20


# ── Ingest lag stats (P3-4.3) ────────────────────────────────────────────────


class TestIngestLagStats:
    def test_returns_none_when_empty(self) -> None:
        store = TelemetryStore()
        assert store.get_ingest_lag_stats() is None

    def test_median_lag_correct(self) -> None:
        store = TelemetryStore()
        # All ships with lag_seconds=5.0 (exact)
        for i in range(10):
            store.ingest(_make_ship(f"L{i}", 55.3, 25.2, offset_minutes=i, lag_seconds=5.0))
        stats = store.get_ingest_lag_stats()
        assert stats is not None
        assert stats.median_lag_seconds == pytest.approx(5.0, abs=0.01)

    def test_p95_at_least_as_large_as_median(self) -> None:
        store = TelemetryStore()
        # Most with small lag, one with large lag (outlier for p95)
        for i in range(20):
            lag = 100.0 if i == 19 else 5.0
            store.ingest(_make_ship(f"P{i}", 55.3, 25.2, offset_minutes=i, lag_seconds=lag))
        stats = store.get_ingest_lag_stats()
        assert stats is not None
        assert stats.p95_lag_seconds >= stats.median_lag_seconds

    def test_sample_count_equals_store_count(self) -> None:
        store = TelemetryStore()
        for i in range(7):
            store.ingest(_make_ship(f"C{i}", 55.3, 25.2, offset_minutes=i, lag_seconds=3.0))
        stats = store.get_ingest_lag_stats()
        assert stats is not None
        assert stats.sample_count == 7

    def test_max_lag_is_largest(self) -> None:
        store = TelemetryStore()
        for i in range(5):
            store.ingest(_make_ship(f"X{i}", 55.3, 25.2, offset_minutes=i, lag_seconds=float(i + 1)))
        stats = store.get_ingest_lag_stats()
        assert stats is not None
        assert stats.max_lag_seconds == pytest.approx(5.0, abs=0.01)


# ── Duplicate + late-arrival handling (P3-4.4) ────────────────────────────────


class TestDuplicateAndLateArrival:
    def test_equal_event_id_never_double_counted(self) -> None:
        store = TelemetryStore()
        ev = _make_ship("LATE1", 55.3, 25.2)
        for _ in range(5):
            store.ingest(ev)
        assert store.count() == 1

    def test_late_arrival_event_stored_correctly(self) -> None:
        """Events that are 'late' (old event_time, recent ingested_at) are accepted.

        Late-arrival flagging is a playback-layer concern; the store itself
        does not filter by ingest order — it accepts all valid positions.
        """
        store = TelemetryStore()
        recent_t = _BASE_TIME
        late_t = _BASE_TIME - timedelta(hours=2)  # older event_time
        ev_late = CanonicalEvent(
            event_id=make_event_id("ais-stream", "LATE2", late_t.isoformat()),
            source="ais-stream",
            source_type=SourceType.TELEMETRY,
            entity_type=EntityType.VESSEL,
            entity_id="LATE2",
            event_type=EventType.SHIP_POSITION,
            event_time=late_t,
            ingested_at=recent_t,  # ingested late
            geometry={"type": "Point", "coordinates": [55.3, 25.2]},
            centroid={"type": "Point", "coordinates": [55.3, 25.2]},
            normalization=NormalizationRecord(normalized_by="ais-stream"),
            provenance=ProvenanceRecord(raw_source_ref="ws://"),
            license=LicenseRecord(),
        )
        assert store.ingest(ev_late) is True
        found = store.query_entity("LATE2", late_t - timedelta(seconds=1), recent_t)
        assert len(found) == 1

    def test_get_entity_ids_filtered_by_source(self) -> None:
        store = TelemetryStore()
        store.ingest(_make_ship("S1", 55.3, 25.2))
        store.ingest(_make_aircraft("AC1", 55.3, 25.2, offset_minutes=1))
        ais_ids = store.get_entity_ids(source="ais-stream")
        osky_ids = store.get_entity_ids(source="opensky")
        assert "S1" in ais_ids
        assert "S1" not in osky_ids
        assert "AC1" in osky_ids

    def test_get_entity_ids_filtered_by_entity_type(self) -> None:
        store = TelemetryStore()
        store.ingest(_make_ship("VESSEL1", 55.3, 25.2))
        store.ingest(_make_aircraft("ICAO001", 55.3, 25.2, offset_minutes=1))
        vessels = store.get_entity_ids(entity_type="vessel")
        aircraft = store.get_entity_ids(entity_type="aircraft")
        assert "VESSEL1" in vessels
        assert "ICAO001" not in vessels
        assert "ICAO001" in aircraft
        assert "VESSEL1" not in aircraft


# ── Interface contract (Phase 0 Track B) ────────────────────────────────────


class TestTelemetryStoreInterfaceContract:
    """Verify TelemetryStore exposes ingest/ingest_batch and NOT upsert.

    These tests guard against accidental regressions where tasks.py would
    call a non-existent method.  They are the canonical contract check for
    Phase 0 Track B.
    """

    def test_ingest_method_exists(self) -> None:
        store = TelemetryStore()
        assert callable(getattr(store, "ingest", None)), \
            "TelemetryStore must have an ingest() method"

    def test_ingest_batch_method_exists(self) -> None:
        store = TelemetryStore()
        assert callable(getattr(store, "ingest_batch", None)), \
            "TelemetryStore must have an ingest_batch() method"

    def test_upsert_method_does_not_exist(self) -> None:
        store = TelemetryStore()
        assert not hasattr(store, "upsert"), \
            "TelemetryStore must NOT expose upsert(); use ingest() instead"

    def test_ingest_returns_bool(self) -> None:
        store = TelemetryStore()
        result = store.ingest(_make_ship("CONTRACT1", 55.3, 25.2))
        assert isinstance(result, bool), \
            f"ingest() must return bool, got {type(result).__name__}"

    def test_ingest_batch_returns_int(self) -> None:
        store = TelemetryStore()
        ships = [_make_ship(f"CB{i}", 55.0 + i * 0.1, 25.0, offset_minutes=i) for i in range(3)]
        result = store.ingest_batch(ships)
        assert isinstance(result, int), \
            f"ingest_batch() must return int, got {type(result).__name__}"


# ── Thread-safety ─────────────────────────────────────────────────────────────


class TestTelemetryStoreThreadSafety:
    def test_concurrent_ingest_no_lost_events(self) -> None:
        store = TelemetryStore()
        errors: List[Exception] = []

        def writer(thread_idx: int) -> None:
            try:
                for j in range(20):
                    store.ingest(_make_ship(f"T{thread_idx}S{j}", 55.0, 25.0, offset_minutes=j))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent ingest raised: {errors}"
        assert store.count() == 100  # 5 threads × 20 unique entities/offsets
