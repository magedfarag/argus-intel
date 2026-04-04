"""Unit tests for the OpenSky aviation connector — P3-2.6.

Tests cover:
- connect() raises ConnectorUnavailableError on HTTP error / auth failure
- fetch() returns empty list on network error
- normalize() converts state vector → aircraft_position CanonicalEvent
- normalize() raises NormalizationError for missing icao24 or null-island
- normalize_all() skips failed records
- build_track_segments() groups aircraft_position events by icao24
- Non-commercial license is enforced on every event
- CorrelationKeys carry icao24 and callsign
- health() returns ConnectorHealthStatus
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorUnavailableError, NormalizationError
from src.connectors.opensky import OpenSkyConnector, _bbox_from_geojson, _haversine_km
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

# OpenSky state vector: 17 elements (index per _COL in opensky.py)
def _make_sv(
    icao24: str = "abc123",
    callsign: str = "SVA001 ",
    country: str = "Saudi Arabia",
    lat: float = 24.80,
    lon: float = 46.67,
    baro_alt: float = 10000.0,
    velocity: float = 250.0,
    on_ground: bool = False,
    time_position: int | None = None,
) -> List[Any]:
    tp = time_position or int(_T0.timestamp())
    return [
        icao24,       # 0: icao24
        callsign,     # 1: callsign
        country,      # 2: origin_country
        tp,           # 3: time_position
        tp,           # 4: last_contact
        lon,          # 5: longitude
        lat,          # 6: latitude
        baro_alt,     # 7: baro_altitude
        on_ground,    # 8: on_ground
        velocity,     # 9: velocity
        90.0,         # 10: true_track
        0.0,          # 11: vertical_rate
        None,         # 12: sensors
        baro_alt,     # 13: geo_altitude
        "1234",       # 14: squawk
        False,        # 15: spi
        0,            # 16: position_source
    ]


def _raw(sv: List[Any] | None = None) -> dict:
    return {
        "_state": sv or _make_sv(),
        "_fetched_at": _T0.isoformat(),
        "_bbox": {},
    }


# ── bbox helper ──────────────────────────────────────────────────────────────

class TestBboxFromGeojson:
    def test_polygon(self) -> None:
        min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(_POLYGON)
        assert min_lat == pytest.approx(24.77)
        assert max_lon == pytest.approx(46.70)

    def test_point(self) -> None:
        min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(
            {"type": "Point", "coordinates": [55.0, 25.0]}
        )
        assert min_lat == pytest.approx(25.0)
        assert min_lon == pytest.approx(55.0)

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            _bbox_from_geojson({"type": "LineString", "coordinates": []})


# ── connect() ────────────────────────────────────────────────────────────────

class TestOpenSkyConnect:
    def test_raises_on_server_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector()
            with pytest.raises(ConnectorUnavailableError, match="unavailable"):
                c.connect()

    def test_raises_on_auth_failure(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector(username="bad", password="creds")
            with pytest.raises(ConnectorUnavailableError, match="authentication"):
                c.connect()

    def test_raises_on_network_error(self) -> None:
        with patch("httpx.get", side_effect=Exception("connection refused")):
            c = OpenSkyConnector()
            with pytest.raises(ConnectorUnavailableError):
                c.connect()

    def test_succeeds_on_200(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector()
            c.connect()
            assert c._connected is True


# ── fetch() ──────────────────────────────────────────────────────────────────

class TestOpenSkyFetch:
    def test_returns_all_state_vectors(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"states": [_make_sv(), _make_sv("def456")]}
        mock_resp.raise_for_status.return_value = None
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector()
            results = c.fetch(_POLYGON, _T0, _T0)
        assert len(results) == 2

    def test_returns_empty_list_on_error(self) -> None:
        with patch("httpx.get", side_effect=Exception("network error")):
            c = OpenSkyConnector()
            results = c.fetch(_POLYGON, _T0, _T0)
        assert results == []

    def test_returns_empty_when_states_null(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"states": None}
        mock_resp.raise_for_status.return_value = None
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector()
            results = c.fetch(_POLYGON, _T0, _T0)
        assert results == []


# ── normalize() ──────────────────────────────────────────────────────────────

class TestOpenSkyNormalize:
    def setup_method(self) -> None:
        self.conn = OpenSkyConnector()

    def test_basic_aircraft_event(self) -> None:
        e = self.conn.normalize(_raw())
        assert e.event_type == EventType.AIRCRAFT_POSITION
        assert e.entity_type == EntityType.AIRCRAFT
        assert e.source == "opensky"

    def test_icao24_in_entity_id(self) -> None:
        e = self.conn.normalize(_raw(_make_sv(icao24="abc123")))
        assert e.entity_id == "abc123"

    def test_icao24_in_correlation_keys(self) -> None:
        e = self.conn.normalize(_raw(_make_sv(icao24="abc123")))
        assert e.correlation_keys.icao24 == "abc123"

    def test_callsign_stripped(self) -> None:
        e = self.conn.normalize(_raw(_make_sv(callsign="SVA001 ")))
        assert e.attributes.get("callsign") == "SVA001"

    def test_position_in_centroid(self) -> None:
        e = self.conn.normalize(_raw(_make_sv(lat=24.80, lon=46.67)))
        coords = e.centroid["coordinates"]
        assert coords[0] == pytest.approx(46.67)
        assert coords[1] == pytest.approx(24.80)

    def test_altitude_in_attributes(self) -> None:
        e = self.conn.normalize(_raw(_make_sv(baro_alt=10500.0)))
        assert e.attributes.get("baro_altitude_m") == pytest.approx(10500.0)

    def test_non_commercial_license(self) -> None:
        e = self.conn.normalize(_raw())
        assert e.license.commercial_use == "not-allowed"

    def test_missing_icao24_raises(self) -> None:
        sv = _make_sv()
        sv[0] = None
        with pytest.raises(NormalizationError, match="icao24"):
            self.conn.normalize(_raw(sv))

    def test_null_island_raises(self) -> None:
        sv = _make_sv(lat=0.0, lon=0.0)
        with pytest.raises(NormalizationError, match="null-island"):
            self.conn.normalize(_raw(sv))

    def test_missing_lat_raises(self) -> None:
        sv = _make_sv()
        sv[6] = None  # latitude
        with pytest.raises(NormalizationError, match="no position"):
            self.conn.normalize(_raw(sv))

    def test_event_time_from_time_position(self) -> None:
        ts = int(_T0.timestamp())
        sv = _make_sv(time_position=ts)
        e = self.conn.normalize(_raw(sv))
        assert e.event_time == _T0


# ── normalize_all() ──────────────────────────────────────────────────────────

class TestOpenSkyNormalizeAll:
    def setup_method(self) -> None:
        self.conn = OpenSkyConnector()

    def test_valid_records_returned(self) -> None:
        recs = [_raw(_make_sv(icao24=f"a{i:05d}")) for i in range(5)]
        events = self.conn.normalize_all(recs)
        assert len(events) == 5

    def test_invalid_records_skipped(self) -> None:
        valid = _raw()
        invalid = {"_state": [None] * 17, "_fetched_at": _T0.isoformat()}
        events = self.conn.normalize_all([valid, invalid])
        assert len(events) == 1

    def test_empty_input(self) -> None:
        assert self.conn.normalize_all([]) == []


# ── build_track_segments() ────────────────────────────────────────────────────

class TestOpenSkyBuildTrackSegments:
    def setup_method(self) -> None:
        self.conn = OpenSkyConnector()

    def _position_events(self, icao24: str = "abc123", count: int = 3) -> list:
        recs = []
        for i in range(count):
            ts_unix = int(_T0.timestamp()) + i * 60
            sv = _make_sv(
                icao24=icao24,
                lat=24.80 + i * 0.01,
                lon=46.67 + i * 0.01,
                time_position=ts_unix,
            )
            recs.append({"_state": sv, "_fetched_at": _T0.isoformat(), "_bbox": {}})
        return self.conn.normalize_all(recs)

    def test_single_aircraft_segment(self) -> None:
        events = self._position_events("abc123", count=3)
        segs = self.conn.build_track_segments(events)
        assert len(segs) == 1
        assert segs[0].event_type == EventType.AIRCRAFT_TRACK_SEGMENT

    def test_insufficient_positions(self) -> None:
        events = self._position_events(count=1)
        segs = self.conn.build_track_segments(events, min_positions=2)
        assert segs == []

    def test_multiple_aircraft_multiple_segments(self) -> None:
        e1 = self._position_events("aaa111", count=3)
        e2 = self._position_events("bbb222", count=3)
        segs = self.conn.build_track_segments(e1 + e2)
        assert len(segs) == 2

    def test_segment_has_time_range(self) -> None:
        events = self._position_events(count=3)
        segs = self.conn.build_track_segments(events)
        assert segs[0].time_start < segs[0].time_end

    def test_segment_distance_positive(self) -> None:
        events = self._position_events(count=3)
        segs = self.conn.build_track_segments(events)
        assert segs[0].attributes["total_distance_km"] > 0


# ── health() ─────────────────────────────────────────────────────────────────

class TestOpenSkyHealth:
    def test_healthy_on_200(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector()
            status = c.health()
        assert status.healthy is True

    def test_unhealthy_on_500(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("httpx.get", return_value=mock_resp):
            c = OpenSkyConnector()
            status = c.health()
        assert status.healthy is False

    def test_unhealthy_on_exception(self) -> None:
        with patch("httpx.get", side_effect=Exception("refused")):
            c = OpenSkyConnector()
            status = c.health()
        assert status.healthy is False
        assert "refused" in status.message
