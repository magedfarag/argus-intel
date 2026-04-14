"""Unit tests for AcledStrikeConnector — STR-04.

Covers:
  - connect() obtains an OAuth2 token and verifies API reachability
  - fetch() returns raw ACLED event dicts from a valid response
  - fetch() raises ConnectorError on HTTP failure
  - normalize() produces valid StrikeEvent objects with correct field mapping
  - event_type mapping for all three ACLED event types (and an unknown type)
  - normalize() fallback strike_id when event_id_cnty is absent
  - fetch_strikes() integrates fetch + normalize and returns list[StrikeEvent]
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.connectors.acled_strike_connector import AcledStrikeConnector
from src.connectors.base import ConnectorError, ConnectorUnavailableError, NormalizationError
from src.models.operational_layers import StrikeEvent

# ── Fixtures ──────────────────────────────────────────────────────────────────

TOKEN_URL = "https://acleddata.com/oauth/token"
API_URL = "https://acleddata.com/api/acled/read"


@pytest.fixture()
def connector() -> AcledStrikeConnector:
    return AcledStrikeConnector(
        email="analyst@example.com",
        password="s3cr3t",
        token_url=TOKEN_URL,
        api_url=API_URL,
    )


@pytest.fixture()
def connector_with_token(connector: AcledStrikeConnector) -> AcledStrikeConnector:
    """Connector with a pre-loaded, non-expired token (skips OAuth2 round-trip)."""
    connector._access_token = "pre-loaded-token"
    connector._token_expires_at = datetime(2099, 1, 1, tzinfo=UTC)
    return connector


# ── Sample ACLED event ────────────────────────────────────────────────────────

_SAMPLE_ACLED_EVENT: dict = {
    "event_id_cnty": "SYR1234",
    "data_id": "9876",
    "event_date": "2026-04-01",
    "latitude": "36.2021",
    "longitude": "37.1343",
    "event_type": "Explosions/Remote violence",
    "country": "Syria",
    "notes": "Airstrike reported on industrial district north of city.",
}


# ── Mock response helpers ────────────────────────────────────────────────────

def _token_resp() -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"access_token": "mock-bearer-token", "expires_in": 86400}
    return m


def _acled_resp(events: list[dict] | None = None, status: int = 200) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"status": status, "data": events or []}
    return m


# ── Constructor validation ────────────────────────────────────────────────────

def test_constructor_requires_email() -> None:
    with pytest.raises(ValueError, match="email"):
        AcledStrikeConnector(email="", password="pw")


def test_constructor_requires_password() -> None:
    with pytest.raises(ValueError, match="password"):
        AcledStrikeConnector(email="x@y.com", password="")


# ── connect() ────────────────────────────────────────────────────────────────

def test_connect_obtains_token_and_probes_api(connector: AcledStrikeConnector) -> None:
    """connect() must call the OAuth2 token endpoint and then verify the API."""
    with patch("httpx.post", return_value=_token_resp()) as mock_post, \
         patch("httpx.get", return_value=_acled_resp()) as mock_get:
        connector.connect()

    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == TOKEN_URL

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args
    assert call_kwargs[0][0] == API_URL or call_kwargs[1].get("url") == API_URL


def test_connect_caches_token(connector: AcledStrikeConnector) -> None:
    """After connect(), the token is cached so subsequent requests skip OAuth2."""
    with patch("httpx.post", return_value=_token_resp()) as mock_post, \
         patch("httpx.get", return_value=_acled_resp()):
        connector.connect()
        assert connector._access_token == "mock-bearer-token"

    # Second call to _get_access_token should NOT re-POST
    with patch("httpx.post") as mock_post2:
        token = connector._get_access_token()
    mock_post2.assert_not_called()
    assert token == "mock-bearer-token"


def test_connect_raises_on_token_http_error(connector: AcledStrikeConnector) -> None:
    with patch("httpx.post", side_effect=httpx.HTTPError("timeout")):
        with pytest.raises(ConnectorUnavailableError):
            connector.connect()


def test_connect_raises_on_api_probe_failure(connector: AcledStrikeConnector) -> None:
    with patch("httpx.post", return_value=_token_resp()), \
         patch("httpx.get", side_effect=httpx.HTTPError("refused")):
        with pytest.raises(ConnectorUnavailableError):
            connector.connect()


# ── fetch() ──────────────────────────────────────────────────────────────────

def test_fetch_returns_raw_event_list(connector_with_token: AcledStrikeConnector) -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)

    with patch("httpx.get", return_value=_acled_resp([_SAMPLE_ACLED_EVENT])):
        result = connector_with_token.fetch({}, start, end)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["event_id_cnty"] == "SYR1234"


def test_fetch_passes_date_range_params(connector_with_token: AcledStrikeConnector) -> None:
    start = datetime(2026, 3, 1, tzinfo=UTC)
    end = datetime(2026, 3, 31, tzinfo=UTC)

    with patch("httpx.get", return_value=_acled_resp()) as mock_get:
        connector_with_token.fetch({}, start, end)

    params = mock_get.call_args[1]["params"]
    assert params["event_date_where"] == "BETWEEN"
    assert "2026-03-01" in params["event_date"]
    assert "2026-03-31" in params["event_date"]


def test_fetch_http_error_raises_connector_error(
    connector_with_token: AcledStrikeConnector,
) -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)

    with patch("httpx.get", side_effect=httpx.HTTPError("connection refused")):
        with pytest.raises(ConnectorError):
            connector_with_token.fetch({}, start, end)


def test_fetch_acled_api_error_raises_connector_error(
    connector_with_token: AcledStrikeConnector,
) -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)

    with patch("httpx.get", return_value=_acled_resp(status=400)):
        with pytest.raises(ConnectorError):
            connector_with_token.fetch({}, start, end)


# ── normalize() ──────────────────────────────────────────────────────────────

def test_normalize_produces_strike_event(connector: AcledStrikeConnector) -> None:
    event = connector.normalize(_SAMPLE_ACLED_EVENT)

    assert isinstance(event, StrikeEvent)
    assert event.strike_id == "SYR1234"
    assert event.occurred_at == datetime(2026, 4, 1, tzinfo=UTC)
    assert event.location_lat == pytest.approx(36.2021)
    assert event.location_lon == pytest.approx(37.1343)
    assert event.strike_type == "airstrike"
    assert event.confidence == 0.75
    assert event.source == "acled"
    assert "SYR1234" in event.provenance
    assert "Syria" in event.provenance
    assert event.corroboration_count == 1


def test_normalize_sets_occurred_at_utc_midnight(connector: AcledStrikeConnector) -> None:
    event = connector.normalize(_SAMPLE_ACLED_EVENT)
    # Spec: UTC midnight (hour=0, not noon)
    assert event.occurred_at.hour == 0
    assert event.occurred_at.minute == 0
    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at.tzinfo == UTC


def test_normalize_notes_in_target_description(connector: AcledStrikeConnector) -> None:
    event = connector.normalize(_SAMPLE_ACLED_EVENT)
    assert event.target_description is not None
    assert "industrial district" in event.target_description


def test_normalize_notes_truncated_to_500(connector: AcledStrikeConnector) -> None:
    long_note = "x" * 600
    raw = dict(_SAMPLE_ACLED_EVENT, notes=long_note)
    event = connector.normalize(raw)
    assert len(event.target_description) == 500


def test_normalize_empty_notes_sets_target_description_none(
    connector: AcledStrikeConnector,
) -> None:
    raw = dict(_SAMPLE_ACLED_EVENT, notes="")
    event = connector.normalize(raw)
    assert event.target_description is None


def test_normalize_fallback_strike_id_when_no_event_id_cnty(
    connector: AcledStrikeConnector,
) -> None:
    raw = {k: v for k, v in _SAMPLE_ACLED_EVENT.items() if k != "event_id_cnty"}
    raw["data_id"] = "99999"
    event = connector.normalize(raw)
    assert event.strike_id == "acled-99999"


def test_normalize_missing_event_date_raises(connector: AcledStrikeConnector) -> None:
    raw = {k: v for k, v in _SAMPLE_ACLED_EVENT.items() if k != "event_date"}
    with pytest.raises(NormalizationError, match="event_date"):
        connector.normalize(raw)


def test_normalize_invalid_date_raises(connector: AcledStrikeConnector) -> None:
    raw = dict(_SAMPLE_ACLED_EVENT, event_date="not-a-date")
    with pytest.raises(NormalizationError):
        connector.normalize(raw)


def test_normalize_missing_coordinates_raises(connector: AcledStrikeConnector) -> None:
    raw = {k: v for k, v in _SAMPLE_ACLED_EVENT.items() if k not in ("latitude", "longitude")}
    with pytest.raises(NormalizationError, match="coordinates"):
        connector.normalize(raw)


# ── Event-type mapping (all 3 types + unknown) ───────────────────────────────

@pytest.mark.parametrize(
    ("acled_event_type", "expected_strike_type"),
    [
        ("Battles", "artillery"),
        ("Explosions/Remote violence", "airstrike"),
        ("Violence against civilians", "unknown"),
        ("Strategic developments", "unknown"),   # unmapped → fallback
        ("", "unknown"),                           # empty string → fallback
    ],
)
def test_event_type_mapping(
    connector: AcledStrikeConnector,
    acled_event_type: str,
    expected_strike_type: str,
) -> None:
    raw = dict(_SAMPLE_ACLED_EVENT, event_type=acled_event_type)
    event = connector.normalize(raw)
    assert event.strike_type == expected_strike_type


# ── fetch_strikes() ──────────────────────────────────────────────────────────

def test_fetch_strikes_returns_strike_event_list(
    connector_with_token: AcledStrikeConnector,
) -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)

    with patch("httpx.get", return_value=_acled_resp([_SAMPLE_ACLED_EVENT])):
        events = connector_with_token.fetch_strikes(start, end)

    assert isinstance(events, list)
    assert len(events) == 1
    assert isinstance(events[0], StrikeEvent)
    assert events[0].strike_id == "SYR1234"


def test_fetch_strikes_applies_region_bbox(
    connector_with_token: AcledStrikeConnector,
) -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)
    # Bounding box that excludes Syria (lon~37, lat~36)
    outside_bbox = (10.0, 40.0, 20.0, 50.0)

    with patch("httpx.get", return_value=_acled_resp([_SAMPLE_ACLED_EVENT])):
        events = connector_with_token.fetch_strikes(start, end, region_bbox=outside_bbox)

    assert events == []


def test_fetch_strikes_skips_malformed_records(
    connector_with_token: AcledStrikeConnector,
) -> None:
    bad_event = {"event_id_cnty": "BAD1", "data_id": "1"}  # missing date and coords
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)

    with patch("httpx.get", return_value=_acled_resp([bad_event, _SAMPLE_ACLED_EVENT])):
        events = connector_with_token.fetch_strikes(start, end)

    # Bad event skipped, good one returned
    assert len(events) == 1
    assert events[0].strike_id == "SYR1234"


def test_fetch_strikes_results_ordered_by_occurred_at(
    connector_with_token: AcledStrikeConnector,
) -> None:
    later_event = dict(_SAMPLE_ACLED_EVENT, event_id_cnty="LATER", event_date="2026-04-05")
    earlier_event = dict(_SAMPLE_ACLED_EVENT, event_id_cnty="EARLIER", event_date="2026-04-02")
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 4, 7, tzinfo=UTC)

    with patch("httpx.get", return_value=_acled_resp([later_event, earlier_event])):
        events = connector_with_token.fetch_strikes(start, end)

    assert events[0].strike_id == "EARLIER"
    assert events[1].strike_id == "LATER"


# ── health() ─────────────────────────────────────────────────────────────────

def test_health_returns_healthy_on_success(
    connector_with_token: AcledStrikeConnector,
) -> None:
    with patch("httpx.get", return_value=_acled_resp()):
        status = connector_with_token.health()

    assert status.healthy is True
    assert status.connector_id == "acled-strike-live"


def test_health_returns_unhealthy_on_error(
    connector_with_token: AcledStrikeConnector,
) -> None:
    with patch("httpx.get", side_effect=httpx.HTTPError("timeout")):
        status = connector_with_token.health()

    assert status.healthy is False
    assert "timeout" in status.message
