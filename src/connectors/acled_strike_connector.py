"""ACLED-backed live strike layer connector — STR-02.

connector_id: ``acled-strike-live``
source_type:  ``public_record``

Fetches battle, explosion, and civilian violence events from the ACLED REST
API and normalises them to ``StrikeEvent`` objects for ``StrikeLayerService``.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE RESTRICTION NOTICE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACLED (Armed Conflict Location & Event Data) is freely available for
non-commercial academic and humanitarian research ONLY.

The following use cases require a SEPARATE WRITTEN AGREEMENT with ACLED
BEFORE any production deployment:
  • AI / ML model training or fine-tuning
  • Competitive intelligence products
  • Any commercial or for-profit application

Verify your access level and permitted use cases at:
  https://acleddata.com/terms-of-use/
  https://acleddata.com/myacled-faqs/

This connector MUST NOT be activated without confirming the deployment's
use case complies with the applicable ACLED licence.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorHealthStatus,
    ConnectorUnavailableError,
    NormalizationError,
)
from src.models.operational_layers import StrikeEvent

log = logging.getLogger(__name__)

_DEFAULT_TOKEN_URL = "https://acleddata.com/oauth/token"
_DEFAULT_API_URL = "https://acleddata.com/api/acled/read"

_SOURCE = "acled"
_PROVENANCE_PREFIX = "acled://events/"
# Fixed confidence for ACLED-sourced events — reflects good but not confirmed data quality.
_ACLED_CONFIDENCE = 0.75

# ACLED event_type → StrikeEvent.strike_type mapping
_STRIKE_TYPE_MAP: dict[str, str] = {
    "Battles": "artillery",
    "Explosions/Remote violence": "airstrike",
    "Violence against civilians": "unknown",
}

# Event types fetched from ACLED (STR-01 assessment)
_FETCH_EVENT_TYPES: list[str] = [
    "Battles",
    "Explosions/Remote violence",
    "Violence against civilians",
]


class AcledStrikeConnector(BaseConnector):
    """Live ACLED-backed connector for the StrikeLayerService.

    Implements the full BaseConnector interface plus the domain-specific
    ``fetch_strikes()`` method used by StrikeLayerService.  OAuth2 password
    grant flow is reused from the pattern established in AcledConnector
    (``src/connectors/acled.py``), but this connector is independent — it
    does NOT share state or token caches with that class.

    Only activated when ``settings.acled_is_configured()`` returns True and the
    application is not running in DEMO mode.  See STR-03 wiring in
    ``src/services/operational_layer_service.py``.
    """

    connector_id: str = "acled-strike-live"
    display_name: str = "ACLED Strike Layer (live)"
    source_type: str = "public_record"

    def __init__(
        self,
        *,
        email: str,
        password: str,
        token_url: str = _DEFAULT_TOKEN_URL,
        api_url: str = _DEFAULT_API_URL,
        http_timeout: float = 30.0,
    ) -> None:
        if not email:
            raise ValueError("AcledStrikeConnector requires a registered ACLED email")
        if not password:
            raise ValueError("AcledStrikeConnector requires an ACLED password")
        self._email = email
        self._password = password
        self._token_url = token_url
        self._api_url = api_url
        self._http_timeout = http_timeout
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    # ── OAuth2 ────────────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Obtain and cache an OAuth2 Bearer token using the password grant flow.

        Token is re-fetched 5 minutes before expiry (ACLED tokens last 24 h).
        """
        if self._access_token and self._token_expires_at:
            if datetime.now(UTC) < self._token_expires_at:
                return self._access_token

        data = {
            "username": self._email,
            "password": self._password,
            "grant_type": "password",
            "client_id": "acled",
        }
        try:
            resp = httpx.post(
                self._token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=data,
                timeout=15.0,
            )
            resp.raise_for_status()
            token_data = resp.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 86400)
            # Refresh 5 minutes early to avoid mid-request expiry.
            self._token_expires_at = (
                datetime.now(UTC).replace(microsecond=0)
                + timedelta(seconds=expires_in - 300)
            )
            return self._access_token
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(
                f"AcledStrikeConnector: failed to obtain token: {exc}"
            ) from exc
        except (KeyError, ValueError) as exc:
            raise ConnectorUnavailableError(
                f"AcledStrikeConnector: invalid token response: {exc}"
            ) from exc

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    # ── BaseConnector interface ───────────────────────────────────────────────

    def connect(self) -> None:
        """Verify ACLED OAuth2 credentials with a minimal probe query (limit=1).

        Raises:
            ConnectorUnavailableError: if auth fails or API is unreachable.
        """
        params: dict[str, Any] = {
            "_format": "json",
            "limit": 1,
            "fields": "event_id_cnty|event_date",
        }
        try:
            resp = httpx.get(
                self._api_url,
                params=params,
                headers=self._auth_headers(),
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != 200:
                raise ConnectorUnavailableError(
                    f"AcledStrikeConnector: auth probe rejected: {data.get('message', data)}"
                )
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(
                f"AcledStrikeConnector: API unreachable: {exc}"
            ) from exc

    def fetch(
        self,
        geometry: dict[str, Any],  # noqa: ARG002
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        """Fetch raw ACLED event dicts for the time window.

        Geometry is accepted for BaseConnector interface compatibility but is
        not used — ACLED events are fetched globally by date range, and the
        StrikeLayerService applies its own regional filtering when needed.
        """
        return self._fetch_by_date_range(start_time, end_time)

    def _fetch_by_date_range(
        self, start_time: datetime, end_time: datetime
    ) -> list[dict[str, Any]]:
        """Call ACLED /acled/read for the configured event types and date window.

        Raises:
            ConnectorError: on HTTP failure or ACLED API-level error.
        """
        date_from = start_time.strftime("%Y-%m-%d")
        date_to = end_time.strftime("%Y-%m-%d")

        params: dict[str, Any] = {
            "_format": "json",
            "event_type": "|".join(_FETCH_EVENT_TYPES),
            "event_date": f"{date_from}|{date_to}",
            "event_date_where": "BETWEEN",
            "limit": 500,
        }
        try:
            resp = httpx.get(
                self._api_url,
                params=params,
                headers=self._auth_headers(),
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"AcledStrikeConnector: fetch failed: {exc}"
            ) from exc

        payload = resp.json()
        if payload.get("status") != 200:
            raise ConnectorError(
                f"AcledStrikeConnector: API error: {payload.get('message', payload)}"
            )
        records: list[dict[str, Any]] = payload.get("data", [])
        log.debug(
            "AcledStrikeConnector: %d events for window %s–%s",
            len(records),
            date_from,
            date_to,
        )
        return records

    def normalize(self, raw: dict[str, Any]) -> StrikeEvent:  # type: ignore[override]
        """Convert a single ACLED event dict to a StrikeEvent.

        Field mapping (STR-01 assessment):
          - strike_id      : event_id_cnty if present, else "acled-{data_id}"
          - occurred_at    : event_date parsed as UTC midnight
          - location_lat/lon : latitude / longitude
          - strike_type    : mapped via _STRIKE_TYPE_MAP; unknown for unmapped types
          - confidence     : fixed 0.75 for all ACLED-sourced events
          - target_description : notes field truncated to 500 chars
          - provenance     : canonical ACLED event URI including country when available

        Raises:
            NormalizationError: if required fields (event_date, coordinates) are absent.
        """
        _eid = raw.get("event_id_cnty")
        strike_id = str(_eid) if _eid else f"acled-{raw.get('data_id', 'unknown')}"

        date_str = raw.get("event_date", "")
        if not date_str:
            raise NormalizationError(
                f"AcledStrikeConnector: missing event_date for event {strike_id!r}"
            )
        try:
            occurred_at = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise NormalizationError(
                f"AcledStrikeConnector: cannot parse date {date_str!r}: {exc}"
            ) from exc

        try:
            location_lat = float(raw["latitude"])
            location_lon = float(raw["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            raise NormalizationError(
                f"AcledStrikeConnector: invalid coordinates for event {strike_id!r}: {exc}"
            ) from exc

        event_type = raw.get("event_type", "")
        strike_type = _STRIKE_TYPE_MAP.get(event_type, "unknown")

        country = raw.get("country", "")
        raw_notes = raw.get("notes") or ""
        notes = raw_notes[:500]

        provenance = f"{_PROVENANCE_PREFIX}{strike_id}"
        if country:
            provenance = f"{_PROVENANCE_PREFIX}{strike_id}?country={country}"

        return StrikeEvent(
            strike_id=strike_id,
            occurred_at=occurred_at,
            location_lat=location_lat,
            location_lon=location_lon,
            location_geojson={
                "type": "Point",
                "coordinates": [location_lon, location_lat],
            },
            strike_type=strike_type,
            target_description=notes if notes else None,
            confidence=_ACLED_CONFIDENCE,
            source=_SOURCE,
            provenance=provenance,
            corroboration_count=1,
        )

    def fetch_strikes(
        self,
        start_time: datetime,
        end_time: datetime,
        region_bbox: tuple[float, float, float, float] | None = None,
    ) -> list[StrikeEvent]:
        """Fetch and normalise ACLED strike events for the time window.

        This is the domain method called by StrikeLayerService (not the
        BaseConnector.fetch() method).

        Args:
            start_time:  Query window start (UTC-aware).
            end_time:    Query window end   (UTC-aware).
            region_bbox: Optional (min_lon, min_lat, max_lon, max_lat) bounding box
                         filter applied post-retrieval.

        Returns:
            List of StrikeEvent instances ordered by occurred_at ascending.
        """
        raw_records = self._fetch_by_date_range(start_time, end_time)
        events: list[StrikeEvent] = []
        for raw in raw_records:
            try:
                event = self.normalize(raw)
                if region_bbox is not None:
                    min_lon, min_lat, max_lon, max_lat = region_bbox
                    if not (
                        min_lon <= event.location_lon <= max_lon
                        and min_lat <= event.location_lat <= max_lat
                    ):
                        continue
                events.append(event)
            except NormalizationError as exc:
                log.warning("AcledStrikeConnector: skipping malformed event — %s", exc)
        events.sort(key=lambda e: e.occurred_at)
        return events

    def health(self) -> ConnectorHealthStatus:
        """Lightweight health probe — authenticated query with limit=1."""
        try:
            params = {
                "_format": "json",
                "limit": 1,
                "fields": "event_id_cnty",
            }
            resp = httpx.get(
                self._api_url,
                params=params,
                headers=self._auth_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=True,
                message="ACLED strike API reachable",
                last_successful_poll=datetime.now(UTC),
            )
        except Exception as exc:  # noqa: BLE001
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
