"""Unit tests for the AIS Stream connector — P3-1.7.

Tests cover:
- connect() raises ConnectorUnavailableError when API key is absent
- normalize() converts AIS message dict → ship_position CanonicalEvent
- normalize() raises NormalizationError for invalid/missing fields
- normalize() discards null-island positions (0.0, 0.0)
- normalize_all() skips failed records and returns valid events
- build_track_segments() groups positions by MMSI and builds segments
- build_track_segments() requires min_positions (default 2)
- health() returns ConnectorHealthStatus
- nav_status codes are mapped to human-readable labels
- MMSI is propagated to CorrelationKeys
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.ais_stream import AisStreamConnector, _bbox_from_geojson, _haversine_km
from src.connectors.base import ConnectorUnavailableError, NormalizationError
from src.models.canonical_event import EventType, EntityType


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


def _make_position_msg(
    mmsi: str = "123456789",
    lat: float = 24.80,
    lon: float = 46.67,
    speed: float = 5.0,
    course: float = 90.0,
    nav_status: int = 0,
    vessel_name: str = "TEST VESSEL",
    timestamp: str | None = None,
) -> dict:
    ts = timestamp or _T0.isoformat()
    return {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": mmsi,
            "ShipName": vessel_name,
            "time_utc": ts,
        },
        "Message": {
            "PositionReport": {
                "UserID": int(mmsi),
                "Latitude": lat,
                "Longitude": lon,
                "SpeedOverGround": speed,
                "CourseOverGround": course,
                "NavigationalStatus": nav_status,
                "TrueHeading": 90,
            }
        },
        "_fetched_at": ts,
    }


# ── connect() ─────────────────────────────────────────────────────────────────

class TestAisStreamConnect:
    def test_raises_when_no_api_key(self) -> None:
        c = AisStreamConnector(api_key="")
        with pytest.raises(ConnectorUnavailableError, match="AISSTREAM_API_KEY"):
            c.connect()

    def test_succeeds_with_api_key(self) -> None:
        c = AisStreamConnector(api_key="test-key-123")
        c.connect()
        assert c._connected is True


# ── Helper utilities ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_bbox_from_polygon(self) -> None:
        min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(_POLYGON)
        assert min_lat == pytest.approx(24.77)
        assert min_lon == pytest.approx(46.65)
        assert max_lat == pytest.approx(24.82)
        assert max_lon == pytest.approx(46.70)

    def test_bbox_from_point(self) -> None:
        geom = {"type": "Point", "coordinates": [46.67, 24.80]}
        min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(geom)
        assert min_lat == pytest.approx(24.80)

    def test_bbox_unsupported_type(self) -> None:
        with pytest.raises(ValueError, match="Unsupported geometry"):
            _bbox_from_geojson({"type": "GeometryCollection", "geometries": []})

    def test_haversine_same_point(self) -> None:
        assert _haversine_km(24.8, 46.67, 24.8, 46.67) == pytest.approx(0.0)

    def test_haversine_known_distance(self) -> None:
        # Riyadh (24.7, 46.7) to ~111 km north
        d = _haversine_km(24.7, 46.7, 25.7, 46.7)
        assert abs(d - 111) < 2  # ±2 km tolerance


# ── normalize() ──────────────────────────────────────────────────────────────

class TestAisNormalize:
    def setup_method(self) -> None:
        self.conn = AisStreamConnector(api_key="test-key")

    def test_basic_position_event(self) -> None:
        msg = _make_position_msg()
        e = self.conn.normalize(msg)
        assert e.event_type == EventType.SHIP_POSITION
        assert e.entity_type == EntityType.VESSEL
        assert e.entity_id == "123456789"
        assert e.source == "ais-stream"

    def test_centroid_matches_position(self) -> None:
        msg = _make_position_msg(lat=24.80, lon=46.67)
        e = self.conn.normalize(msg)
        coords = e.centroid["coordinates"]
        assert coords[0] == pytest.approx(46.67)
        assert coords[1] == pytest.approx(24.80)

    def test_mmsi_in_correlation_keys(self) -> None:
        e = self.conn.normalize(_make_position_msg(mmsi="987654321"))
        assert e.correlation_keys.mmsi == "987654321"

    def test_speed_and_course_attributes(self) -> None:
        msg = _make_position_msg(speed=12.5, course=270.0)
        e = self.conn.normalize(msg)
        assert e.attributes["speed_kn"] == pytest.approx(12.5)
        assert e.attributes["course_deg"] == pytest.approx(270.0)

    def test_nav_status_label(self) -> None:
        msg = _make_position_msg(nav_status=5)  # Moored
        e = self.conn.normalize(msg)
        assert e.attributes["nav_status"] == "Moored"

    def test_nav_status_unknown_code(self) -> None:
        msg = _make_position_msg(nav_status=99)
        e = self.conn.normalize(msg)
        assert e.attributes["nav_status"] == "Undefined"

    def test_missing_mmsi_raises(self) -> None:
        msg = _make_position_msg()
        msg["MetaData"]["MMSI"] = None
        msg["Message"]["PositionReport"]["UserID"] = None
        with pytest.raises(NormalizationError, match="MMSI"):
            self.conn.normalize(msg)

    def test_null_island_raises(self) -> None:
        msg = _make_position_msg(lat=0.0, lon=0.0)
        with pytest.raises(NormalizationError, match="null-island"):
            self.conn.normalize(msg)

    def test_event_time_from_metadata(self) -> None:
        ts = "2026-04-01T10:00:00+00:00"
        msg = _make_position_msg(timestamp=ts)
        e = self.conn.normalize(msg)
        assert e.event_time == datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)

    def test_license_is_public(self) -> None:
        e = self.conn.normalize(_make_position_msg())
        assert e.license.access_tier == "public"

    def test_vessel_name_in_attributes(self) -> None:
        msg = _make_position_msg(vessel_name="CARGO QUEEN")
        e = self.conn.normalize(msg)
        assert e.attributes.get("vessel_name") == "CARGO QUEEN"


# ── normalize_all() ───────────────────────────────────────────────────────────

class TestAisNormalizeAll:
    def setup_method(self) -> None:
        self.conn = AisStreamConnector(api_key="test-key")

    def test_valid_records_returned(self) -> None:
        msgs = [_make_position_msg(mmsi=str(i + 100000000)) for i in range(5)]
        events = self.conn.normalize_all(msgs)
        assert len(events) == 5

    def test_invalid_records_skipped(self) -> None:
        valid = _make_position_msg()
        invalid = {"MessageType": "PositionReport", "MetaData": {}, "Message": {}}
        events = self.conn.normalize_all([valid, invalid])
        assert len(events) == 1

    def test_empty_input(self) -> None:
        assert self.conn.normalize_all([]) == []


# ── build_track_segments() ────────────────────────────────────────────────────

class TestAisBuildTrackSegments:
    def setup_method(self) -> None:
        self.conn = AisStreamConnector(api_key="test-key")

    def _position_events(self, mmsi: str = "111111111", count: int = 3) -> list:
        msgs = []
        for i in range(count):
            ts = f"2026-04-01T{10 + i:02d}:00:00+00:00"
            msgs.append(
                _make_position_msg(
                    mmsi=mmsi,
                    lat=24.80 + i * 0.01,
                    lon=46.67 + i * 0.01,
                    timestamp=ts,
                )
            )
        return self.conn.normalize_all(msgs)

    def test_single_mmsi_produces_one_segment(self) -> None:
        events = self._position_events("111111111", count=3)
        segments = self.conn.build_track_segments(events)
        assert len(segments) == 1

    def test_segment_event_type(self) -> None:
        events = self._position_events(count=4)
        segs = self.conn.build_track_segments(events)
        assert segs[0].event_type == EventType.SHIP_TRACK_SEGMENT

    def test_segment_time_range(self) -> None:
        events = self._position_events(count=3)
        segs = self.conn.build_track_segments(events)
        assert segs[0].time_start is not None
        assert segs[0].time_end is not None
        assert segs[0].time_start < segs[0].time_end

    def test_min_positions_not_met_returns_empty(self) -> None:
        events = self._position_events(count=1)
        segs = self.conn.build_track_segments(events, min_positions=2)
        assert segs == []

    def test_multiple_mmsi_multiple_segments(self) -> None:
        e1 = self._position_events("111111111", count=3)
        e2 = self._position_events("222222222", count=3)
        segs = self.conn.build_track_segments(e1 + e2)
        assert len(segs) == 2

    def test_segment_has_distance(self) -> None:
        events = self._position_events(count=3)
        segs = self.conn.build_track_segments(events)
        assert segs[0].attributes["total_distance_km"] > 0


# ── health() ─────────────────────────────────────────────────────────────────

class TestAisHealth:
    def test_no_api_key_unhealthy(self) -> None:
        c = AisStreamConnector(api_key="")
        status = c.health()
        assert status.healthy is False
        assert "API key" in status.message

    def test_healthy_when_api_key_and_http_ok(self) -> None:
        c = AisStreamConnector(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp):
            status = c.health()
        assert status.healthy is True

    def test_unhealthy_on_http_error(self) -> None:
        c = AisStreamConnector(api_key="test-key")
        with patch("httpx.get", side_effect=Exception("timeout")):
            status = c.health()
        assert status.healthy is False
        assert "timeout" in status.message
