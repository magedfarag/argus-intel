"""Unit tests for CelestrakConnector — ORB-04.

Coverage:
- fetch() returns expected list[dict] structure from mock TLE response.
- fetch() raises ConnectorError on HTTP 5xx error.
- fetch() raises ConnectorError on network-level failure.
- normalize() produces a valid CanonicalEvent from a raw TLE dict.
- normalize() raises NormalizationError when required fields are missing.
- health() reflects connected/error state correctly.
- fetch_all_tles() returns SatelliteOrbit objects with source stamped correctly.
- ingest_orbits() parses an explicit TLE block and re-stamps source.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.connectors.base import ConnectorError, NormalizationError
from src.connectors.celestrak_connector import CelestrakConnector, _parse_tle_text
from src.models.canonical_event import CanonicalEvent, EventType


# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_TLE = """\
ISS (ZARYA)
1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994
2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123
SENTINEL-2A
1 40697U 15028A   26094.50000000  .00000050  00000-0  17800-4 0  9991
2 40697  98.5683  62.2784 0001123  84.5271 275.6031 14.30820001562811
"""


def _mock_ok_response(text: str = _SAMPLE_TLE) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


def _mock_error_response(status_code: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    )
    return resp


# ── _parse_tle_text ───────────────────────────────────────────────────────────


def test_parse_tle_text_returns_dicts():
    result = _parse_tle_text(_SAMPLE_TLE)
    assert len(result) == 2
    assert result[0]["name"] == "ISS (ZARYA)"
    assert result[0]["line1"].startswith("1 25544")
    assert result[0]["line2"].startswith("2 25544")
    assert result[1]["name"] == "SENTINEL-2A"


def test_parse_tle_text_skips_blank_and_comment_lines():
    text = "# comment\n\n" + _SAMPLE_TLE
    result = _parse_tle_text(text)
    assert len(result) == 2


def test_parse_tle_text_discards_partial_triplet():
    # Only two lines after the first triplet — should be discarded.
    text = _SAMPLE_TLE + "ORPHAN\n1 99999U ...\n"
    result = _parse_tle_text(text)
    assert len(result) == 2


# ── CelestrakConnector.fetch() ────────────────────────────────────────────────


def test_fetch_returns_expected_structure():
    conn = CelestrakConnector(timeout=5)
    with patch("src.connectors.celestrak_connector.httpx.get", return_value=_mock_ok_response()):
        result = conn.fetch({}, datetime.now(UTC), datetime.now(UTC))

    assert len(result) == 2
    for item in result:
        assert "name" in item
        assert "line1" in item
        assert "line2" in item
        assert item["line1"].startswith("1 ")
        assert item["line2"].startswith("2 ")


def test_fetch_raises_connector_error_on_http_500():
    conn = CelestrakConnector(timeout=5)
    with patch(
        "src.connectors.celestrak_connector.httpx.get",
        return_value=_mock_error_response(500),
    ):
        with pytest.raises(ConnectorError, match="HTTP 500"):
            conn.fetch({}, datetime.now(UTC), datetime.now(UTC))

    assert conn._error_count == 1


def test_fetch_raises_connector_error_on_network_failure():
    conn = CelestrakConnector(timeout=5)
    with patch(
        "src.connectors.celestrak_connector.httpx.get",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        with pytest.raises(ConnectorError, match="network failure"):
            conn.fetch({}, datetime.now(UTC), datetime.now(UTC))

    assert conn._error_count == 1


# ── CelestrakConnector.normalize() ───────────────────────────────────────────


def test_normalize_produces_canonical_event():
    conn = CelestrakConnector()
    raw = {
        "name": "ISS (ZARYA)",
        "line1": "1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994",
        "line2": "2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123",
    }
    event = conn.normalize(raw)
    assert isinstance(event, CanonicalEvent)
    assert event.event_type == EventType.SATELLITE_ORBIT
    assert event.attributes["satellite_id"] == "ISS-(ZARYA)"
    assert event.attributes["norad_id"] == 25544


def test_normalize_raises_on_missing_name():
    conn = CelestrakConnector()
    raw = {
        "line1": "1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994",
        "line2": "2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123",
    }
    with pytest.raises(NormalizationError, match="missing field"):
        conn.normalize(raw)


def test_normalize_raises_on_missing_line1():
    conn = CelestrakConnector()
    raw = {
        "name": "ISS (ZARYA)",
        "line2": "2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123",
    }
    with pytest.raises(NormalizationError):
        conn.normalize(raw)


# ── CelestrakConnector.health() ──────────────────────────────────────────────


def test_health_not_connected_by_default():
    conn = CelestrakConnector()
    status = conn.health()
    assert status.connector_id == "celestrak-gp-live"
    assert not status.healthy
    assert "Not yet connected" in status.message


def test_health_connected_no_errors():
    conn = CelestrakConnector()
    conn._connected = True
    status = conn.health()
    assert status.healthy
    assert status.error_count == 0


def test_health_connected_with_errors():
    conn = CelestrakConnector()
    conn._connected = True
    conn._error_count = 2
    status = conn.health()
    assert not status.healthy
    assert status.error_count == 2


# ── CelestrakConnector.fetch_all_tles() ──────────────────────────────────────


def test_fetch_all_tles_returns_satellite_orbit_objects():
    conn = CelestrakConnector(timeout=5)
    with patch("src.connectors.celestrak_connector.httpx.get", return_value=_mock_ok_response()):
        orbits = conn.fetch_all_tles()

    assert len(orbits) == 2
    sat_ids = {o.satellite_id for o in orbits}
    assert "ISS-(ZARYA)" in sat_ids
    assert "SENTINEL-2A" in sat_ids


def test_fetch_all_tles_stamps_live_source():
    conn = CelestrakConnector(timeout=5)
    with patch("src.connectors.celestrak_connector.httpx.get", return_value=_mock_ok_response()):
        orbits = conn.fetch_all_tles()

    for orbit in orbits:
        assert orbit.source == "celestrak_gp_live"


def test_fetch_all_tles_sets_last_success():
    conn = CelestrakConnector(timeout=5)
    assert conn._last_success is None
    with patch("src.connectors.celestrak_connector.httpx.get", return_value=_mock_ok_response()):
        conn.fetch_all_tles()
    assert conn._last_success is not None


# ── CelestrakConnector.ingest_orbits() ───────────────────────────────────────


def test_ingest_orbits_parses_tle_text():
    conn = CelestrakConnector()
    orbits = conn.ingest_orbits(_SAMPLE_TLE)
    assert len(orbits) == 2


def test_ingest_orbits_stamps_live_source():
    conn = CelestrakConnector()
    orbits = conn.ingest_orbits(_SAMPLE_TLE)
    for orbit in orbits:
        assert orbit.source == "celestrak_gp_live"
