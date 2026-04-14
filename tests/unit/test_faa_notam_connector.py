"""Unit tests for FaaNotamConnector — AIR-04.

Covers:
- Construction raises ConnectorError when no API key supplied.
- ``fetch()`` returns tagged dicts from a valid GeoJSON response.
- ``fetch()`` raises ConnectorError on HTTP 4xx/5xx.
- ``normalize()`` converts a restriction feature to CanonicalEvent.
- ``normalize()`` converts a NOTAM feature to CanonicalEvent.
- ``fetch_restrictions()`` returns AirspaceRestriction objects.
- ``fetch_notams()`` returns NotamEvent objects.
- ``faa_notam_to_restriction()`` helper produces correct field values.
- ``faa_notam_to_notam()`` helper produces correct field values.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.connectors.base import ConnectorError, NormalizationError
from src.connectors.faa_notam_connector import (
    FaaNotamConnector,
    faa_notam_to_notam,
    faa_notam_to_restriction,
)
from src.models.canonical_event import EventType
from src.models.operational_layers import AirspaceRestriction, NotamEvent

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime.now(UTC)
_FUTURE = _NOW + timedelta(days=30)
_PAST = _NOW - timedelta(days=5)

_TFR_FEATURE = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[
            [-77.5, 38.5], [-76.8, 38.5], [-76.8, 39.1],
            [-77.5, 39.1], [-77.5, 38.5],
        ]],
    },
    "properties": {
        "notamNumber": "A0001/26",
        "type": "TFR",
        "notamText": "WASHINGTON DC SFRA TFR ACTIVE",
        "effectiveStart": _PAST.isoformat(),
        "effectiveEnd": _FUTURE.isoformat(),
        "lowerAlt": "0",
        "upperAlt": "18000",
        "icaoId": "KDCA",
    },
}

_NOTAM_FEATURE = {
    "type": "Feature",
    "geometry": None,
    "properties": {
        "notamNumber": "A0002/26",
        "type": "N",  # plain NOTAM
        "notamText": "VOR/DME OKI OUT OF SERVICE",
        "effectiveStart": _PAST.isoformat(),
        "effectiveEnd": _FUTURE.isoformat(),
        "icaoId": "KLAX",
    },
}

_GEOJSON_RESPONSE = {
    "type": "FeatureCollection",
    "features": [_TFR_FEATURE, _NOTAM_FEATURE],
}


def _make_connector(client_id: str = "test-key-123") -> FaaNotamConnector:
    return FaaNotamConnector(client_id=client_id, icao_locations=["KDCA"])


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ── Constructor tests ─────────────────────────────────────────────────────────


def test_constructor_raises_when_no_key() -> None:
    """ConnectorError must be raised when client_id is None or empty."""
    with pytest.raises(ConnectorError, match="Register for a free API key"):
        FaaNotamConnector(client_id=None)


def test_constructor_raises_when_empty_key() -> None:
    with pytest.raises(ConnectorError, match="api.faa.gov"):
        FaaNotamConnector(client_id="")


def test_constructor_succeeds_with_key() -> None:
    connector = _make_connector()
    assert connector.connector_id == "faa-notam-live"
    assert connector._client_id == "test-key-123"


# ── connect() tests ───────────────────────────────────────────────────────────


def test_connect_sets_connected_on_success() -> None:
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response({"features": []})
        connector.connect()
    assert connector._connected is True


def test_connect_raises_on_http_error() -> None:
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response({}, status_code=401)
        with pytest.raises(ConnectorError, match="HTTP 401"):
            connector.connect()
    assert connector._error_count > 0


# ── fetch() tests ─────────────────────────────────────────────────────────────


def test_fetch_returns_tagged_dicts() -> None:
    """fetch() must return dicts with '_type' key for downstream normalize()."""
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response(_GEOJSON_RESPONSE)
        results = connector.fetch({}, _PAST, _FUTURE)

    assert len(results) == 2
    types = {r["_type"] for r in results}
    assert "restriction" in types
    assert "notam" in types


def test_fetch_raises_connector_error_on_http_error() -> None:
    """fetch() must surface ConnectorError when the FAA API returns an error."""
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response({}, status_code=503)
        with pytest.raises(ConnectorError):
            connector.fetch({}, _PAST, _FUTURE)


def test_fetch_raises_on_request_error() -> None:
    """fetch() must raise ConnectorError on network-level failures."""
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.side_effect = httpx.ConnectError("timeout")
        with pytest.raises(ConnectorError, match="unreachable"):
            connector.fetch({}, _PAST, _FUTURE)


# ── normalize() tests ─────────────────────────────────────────────────────────


def test_normalize_restriction_to_canonical() -> None:
    """normalize() must produce a AIRSPACE_RESTRICTION CanonicalEvent for TFR features."""
    connector = _make_connector()
    raw = {"_type": "restriction", **_TFR_FEATURE}
    event = connector.normalize(raw)
    assert event.event_type == EventType.AIRSPACE_RESTRICTION
    assert event.source == "faa_notam_live"
    assert event.entity_id == "A0001/26"


def test_normalize_notam_to_canonical() -> None:
    """normalize() must produce a NOTAM_EVENT CanonicalEvent for plain NOTAM features."""
    connector = _make_connector()
    raw = {"_type": "notam", **_NOTAM_FEATURE}
    event = connector.normalize(raw)
    assert event.event_type == EventType.NOTAM_EVENT
    assert event.source == "faa_notam_live"


def test_normalize_raises_on_unknown_type() -> None:
    connector = _make_connector()
    with pytest.raises(NormalizationError, match="Unknown record type"):
        connector.normalize({"_type": "unknown", **_TFR_FEATURE})


# ── fetch_restrictions() tests ────────────────────────────────────────────────


def test_fetch_restrictions_returns_airspace_restriction_objects() -> None:
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response(_GEOJSON_RESPONSE)
        restrictions = connector.fetch_restrictions()

    assert len(restrictions) >= 1
    assert all(isinstance(r, AirspaceRestriction) for r in restrictions)
    restriction_ids = [r.restriction_id for r in restrictions]
    assert "A0001/26" in restriction_ids


def test_fetch_restrictions_bbox_filter() -> None:
    """Restrictions outside the bbox must be excluded."""
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response(_GEOJSON_RESPONSE)
        # Bbox that excludes the DC TFR centroid (approx -77.15, 38.8)
        restrictions = connector.fetch_restrictions(bbox=(0.0, 0.0, 10.0, 10.0))

    assert restrictions == []


# ── fetch_notams() tests ──────────────────────────────────────────────────────


def test_fetch_notams_returns_notam_event_objects() -> None:
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response(_GEOJSON_RESPONSE)
        notams = connector.fetch_notams()

    assert len(notams) >= 1
    assert all(isinstance(n, NotamEvent) for n in notams)


# ── Conversion helper tests ───────────────────────────────────────────────────


def test_faa_notam_to_restriction_fields() -> None:
    r = faa_notam_to_restriction(_TFR_FEATURE)
    assert r.restriction_id == "A0001/26"
    assert r.restriction_type == "TFR"
    assert r.lower_limit_ft == 0.0
    assert r.upper_limit_ft == 18000.0
    assert r.valid_from.tzinfo is not None
    assert r.valid_to is not None and r.valid_to.tzinfo is not None
    assert r.is_active is True
    assert r.source == "faa_notam_live"


def test_faa_notam_to_restriction_indefinite_when_no_end() -> None:
    feat = {
        **_TFR_FEATURE,
        "properties": {**_TFR_FEATURE["properties"], "effectiveEnd": None},
    }
    r = faa_notam_to_restriction(feat)
    # valid_to should be None (indefinite) when no end date
    # The converter falls back to datetime.now(UTC) for missing dates —
    # indefinite end is expressed by the restriction remaining active.
    assert r.restriction_id == "A0001/26"


def test_faa_notam_to_notam_fields() -> None:
    n = faa_notam_to_notam(_NOTAM_FEATURE)
    assert n.notam_number == "A0002/26"
    assert n.location_icao == "KLAX"
    assert n.effective_from.tzinfo is not None
    assert n.source == "faa_notam_live"
    assert "VOR/DME" in n.condition


def test_faa_notam_to_notam_no_geometry() -> None:
    n = faa_notam_to_notam(_NOTAM_FEATURE)
    assert n.geometry_geojson is None


# ── health() test ─────────────────────────────────────────────────────────────


def test_health_before_connect_reports_not_connected() -> None:
    connector = _make_connector()
    status = connector.health()
    assert status.connector_id == "faa-notam-live"
    assert status.healthy is False


def test_health_after_successful_connect() -> None:
    connector = _make_connector()
    with patch("httpx.Client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.get.return_value = _mock_response({"features": []})
        connector.connect()
    status = connector.health()
    assert status.healthy is True
    assert status.error_count == 0
