"""Live FAA NOTAM connector — AIR-01 / AIR-02.

Fetches airspace restrictions and NOTAMs from the FAA NOTAM Search API
(https://external-api.faa.gov/notamSearch/api/notams) using a free API key
obtained at https://api.faa.gov/.

connector_id: ``faa-notam-live``
source_type:  ``context_feed``

Design notes:
- ``connect()`` validates that the API key is present and performs a lightweight
  health-check probe against the FAA endpoint. Raises ``ConnectorError`` with a
  signup hint when no key is configured.
- ``fetch()`` satisfies the ``BaseConnector`` abstract interface; it accepts the
  standard geometry / time-window parameters but internally delegates to
  ``fetch_restrictions()`` and ``fetch_notams()`` which the
  ``AirspaceLayerService.refresh()`` calls directly.
- ``normalize()`` dispatches by the ``_type`` key injected by ``fetch()``,
  matching the contract used by the stub connector.
- All datetime fields are UTC-aware.
- HTTP calls use ``httpx`` (the project's standard HTTP client).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorHealthStatus,
    NormalizationError,
)
from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.models.operational_layers import AirspaceRestriction, NotamEvent

logger = logging.getLogger(__name__)

_SOURCE = "faa_notam_live"
_BASE_URL = "https://external-api.faa.gov/notamSearch/api/notams"
_SIGNUP_URL = "https://api.faa.gov/"

# FAA NOTAM data is public; mark conservative redistribution terms.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)

# Default ICAO locations queried when no specific location is requested.
_DEFAULT_ICAO_LOCATIONS = ["KDCA", "KJFK", "KLAX", "KORD", "KATL"]


def faa_notam_to_restriction(raw: dict[str, Any]) -> AirspaceRestriction:
    """Convert a raw FAA NOTAM GeoJSON feature to an ``AirspaceRestriction``.

    Handles features where ``properties.type`` indicates a TFR, MOA, NFZ, or
    ADIZ.  Returns an ``AirspaceRestriction`` with UTC-aware datetimes.
    """
    props = raw.get("properties", {})
    geometry = raw.get("geometry") or {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]],
    }

    notam_number: str = props.get("notamNumber") or props.get("notam_number") or "UNKNOWN"
    restriction_type: str = (props.get("type") or props.get("classification") or "TFR").upper()

    valid_from = _parse_dt(props.get("effectiveStart") or props.get("startDate"))
    valid_to = _parse_dt(props.get("effectiveEnd") or props.get("endDate"))

    lower_str = props.get("lowerAlt") or props.get("minimumAltitude")
    upper_str = props.get("upperAlt") or props.get("maximumAltitude")

    return AirspaceRestriction(
        restriction_id=notam_number,
        name=props.get("notamText", "")[:120] or notam_number,
        restriction_type=restriction_type,
        geometry_geojson=geometry,
        lower_limit_ft=_parse_alt_ft(lower_str),
        upper_limit_ft=_parse_alt_ft(upper_str),
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=_is_active(valid_from, valid_to),
        source=_SOURCE,
        provenance=f"https://external-api.faa.gov/notamSearch/api/notams?notamNumber={notam_number}",
    )


def faa_notam_to_notam(raw: dict[str, Any]) -> NotamEvent:
    """Convert a raw FAA NOTAM GeoJSON feature to a ``NotamEvent``."""
    props = raw.get("properties", {})
    geometry = raw.get("geometry")

    notam_number: str = props.get("notamNumber") or props.get("notam_number") or "UNKNOWN"
    notam_id = f"faa-live-{notam_number}"

    effective_from = _parse_dt(props.get("effectiveStart") or props.get("startDate"))
    effective_to = _parse_dt(props.get("effectiveEnd") or props.get("endDate"))

    return NotamEvent(
        notam_id=notam_id,
        notam_number=notam_number,
        subject=props.get("subject") or props.get("classification") or "FAA NOTAM",
        condition=props.get("notamText", "")[:500] or notam_number,
        location_icao=props.get("icaoId") or props.get("location"),
        effective_from=effective_from,
        effective_to=effective_to,
        geometry_geojson=geometry,
        raw_text=props.get("notamText"),
        source=_SOURCE,
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _parse_dt(value: str | None) -> datetime:
    """Parse an ISO-8601 / FAA datetime string to a UTC-aware datetime.

    Falls back to ``datetime.now(UTC)`` when the value is absent or invalid.
    """
    if not value:
        return datetime.now(UTC)
    # FAA API may return strings like "2026-04-14T12:00:00.000Z" or "2026-04-14T12:00:00"
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, AttributeError):
        return datetime.now(UTC)


def _parse_alt_ft(value: str | int | float | None) -> float | None:
    """Convert an altitude value to feet as a float, or None."""
    if value is None:
        return None
    try:
        return float(str(value).replace("FT", "").replace("ft", "").strip())
    except (ValueError, TypeError):
        return None


def _is_active(valid_from: datetime, valid_to: datetime | None) -> bool:
    now = datetime.now(UTC)
    if valid_from > now:
        return False
    if valid_to is not None and valid_to <= now:
        return False
    return True


def _restriction_to_canonical(r: AirspaceRestriction) -> CanonicalEvent:
    geojson = r.geometry_geojson
    coords = geojson.get("coordinates", [[]])[0]
    if coords:
        avg_lon = sum(c[0] for c in coords) / len(coords)
        avg_lat = sum(c[1] for c in coords) / len(coords)
        centroid: dict[str, Any] = {
            "type": "Point",
            "coordinates": [round(avg_lon, 4), round(avg_lat, 4)],
        }
    else:
        centroid = {"type": "Point", "coordinates": [0.0, 0.0]}

    event_id = make_event_id(_SOURCE, r.restriction_id, r.valid_from)
    return CanonicalEvent(
        event_id=event_id,
        source=_SOURCE,
        source_type=SourceType.CONTEXT_FEED,
        entity_type=EntityType.SYSTEM,
        entity_id=r.restriction_id,
        event_type=EventType.AIRSPACE_RESTRICTION,
        event_time=r.valid_from,
        time_start=r.valid_from,
        time_end=r.valid_to,
        geometry=geojson,
        centroid=centroid,
        confidence=1.0,
        attributes={
            "restriction_id": r.restriction_id,
            "name": r.name,
            "restriction_type": r.restriction_type,
            "lower_limit_ft": r.lower_limit_ft,
            "upper_limit_ft": r.upper_limit_ft,
            "is_active": r.is_active,
        },
        normalization=NormalizationRecord(normalized_by="connector.faa_notam_live"),
        provenance=ProvenanceRecord(
            raw_source_ref=r.provenance or f"faa-notam-live://{r.restriction_id}",
            source_record_id=r.restriction_id,
        ),
        license=_LICENSE,
    )


def _notam_to_canonical(n: NotamEvent) -> CanonicalEvent:
    if n.geometry_geojson:
        geometry: dict[str, Any] = n.geometry_geojson
        coords = geometry.get("coordinates", [[]])[0]
        if coords:
            avg_lon = sum(c[0] for c in coords) / len(coords)
            avg_lat = sum(c[1] for c in coords) / len(coords)
            centroid: dict[str, Any] = {
                "type": "Point",
                "coordinates": [round(avg_lon, 4), round(avg_lat, 4)],
            }
        else:
            centroid = {"type": "Point", "coordinates": [0.0, 0.0]}
    else:
        geometry = {"type": "Point", "coordinates": [0.0, 0.0]}
        centroid = {"type": "Point", "coordinates": [0.0, 0.0]}

    event_id = make_event_id(_SOURCE, n.notam_id, n.effective_from)
    return CanonicalEvent(
        event_id=event_id,
        source=_SOURCE,
        source_type=SourceType.CONTEXT_FEED,
        entity_type=EntityType.SYSTEM,
        entity_id=n.notam_id,
        event_type=EventType.NOTAM_EVENT,
        event_time=n.effective_from,
        time_start=n.effective_from,
        time_end=n.effective_to,
        geometry=geometry,
        centroid=centroid,
        confidence=1.0,
        attributes={
            "notam_id": n.notam_id,
            "notam_number": n.notam_number,
            "subject": n.subject,
            "condition": n.condition,
            "location_icao": n.location_icao,
        },
        normalization=NormalizationRecord(normalized_by="connector.faa_notam_live"),
        provenance=ProvenanceRecord(
            raw_source_ref=f"faa-notam-live://{n.notam_id}",
            source_record_id=n.notam_id,
        ),
        license=_LICENSE,
    )


# ── Connector ─────────────────────────────────────────────────────────────────


class FaaNotamConnector(BaseConnector):
    """Live FAA NOTAM Search API connector (AIR-01).

    Requires a free API key from https://api.faa.gov/.  Set it via the
    ``FAA_NOTAM_CLIENT_ID`` environment variable or ``AppSettings``.

    When ``client_id`` is ``None`` or empty, ``connect()`` raises
    ``ConnectorError`` with instructions for obtaining a free key.
    """

    connector_id: str = "faa-notam-live"
    display_name: str = "FAA NOTAM Live"
    source_type: str = "context_feed"

    def __init__(
        self,
        client_id: str | None,
        timeout: float = 30.0,
        icao_locations: list[str] | None = None,
    ) -> None:
        if not client_id:
            raise ConnectorError(
                "FAA NOTAM client_id is required. "
                f"Register for a free API key at {_SIGNUP_URL} "
                "and set FAA_NOTAM_CLIENT_ID in your environment."
            )
        self._client_id = client_id
        self._timeout = timeout
        self._icao_locations = icao_locations or _DEFAULT_ICAO_LOCATIONS
        self._last_poll: datetime | None = None
        self._error_count: int = 0
        self._connected: bool = False

    # ── BaseConnector abstract methods ────────────────────────────────────

    def connect(self) -> None:
        """Probe the FAA endpoint with a lightweight request to verify connectivity."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    _BASE_URL,
                    headers={"client_id": self._client_id},
                    params={"icaoLocation": "KDCA", "responseFormat": "geoJson", "pageSize": "1"},
                )
                resp.raise_for_status()
            self._connected = True
            logger.info("FaaNotamConnector: connected to FAA NOTAM API")
        except httpx.HTTPStatusError as exc:
            self._error_count += 1
            raise ConnectorError(
                f"FAA NOTAM API returned HTTP {exc.response.status_code}. "
                "Check your client_id at https://api.faa.gov/"
            ) from exc
        except httpx.RequestError as exc:
            self._error_count += 1
            raise ConnectorError(f"FAA NOTAM API unreachable: {exc}") from exc

    def fetch(
        self,
        geometry: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch raw NOTAM GeoJSON features and tag each with ``_type``.

        Internally loops over ``_icao_locations``; deduplicates by notamNumber.
        Returns records tagged for downstream ``normalize()`` dispatch.
        """
        features = self._fetch_features()
        results: list[dict[str, Any]] = []
        for feat in features:
            props = feat.get("properties", {})
            notam_type = (
                props.get("type") or props.get("classification") or ""
            ).upper()
            if notam_type in {"TFR", "MOA", "NFZ", "ADIZ", "CTR", "P", "R"}:
                results.append({"_type": "restriction", **feat})
            else:
                results.append({"_type": "notam", **feat})
        return results

    def normalize(self, raw: dict[str, Any]) -> CanonicalEvent:
        """Normalize a tagged FAA NOTAM feature dict to a ``CanonicalEvent``."""
        record_type = raw.get("_type")
        clean = {k: v for k, v in raw.items() if k != "_type"}
        try:
            if record_type == "restriction":
                r = faa_notam_to_restriction(clean)
                return _restriction_to_canonical(r)
            elif record_type == "notam":
                n = faa_notam_to_notam(clean)
                return _notam_to_canonical(n)
            else:
                raise NormalizationError(f"Unknown record type: {record_type!r}")
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(f"Cannot normalize FAA NOTAM record: {exc}") from exc

    def health(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=self._connected,
            message="OK" if self._connected else "Not connected",
            last_successful_poll=self._last_poll,
            error_count=self._error_count,
        )

    # ── AirspaceLayerService interface ────────────────────────────────────

    def fetch_restrictions(
        self,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[AirspaceRestriction]:
        """Fetch active restrictions from the FAA API.

        Args:
            bbox: Optional ``(min_lon, min_lat, max_lon, max_lat)`` bounding box.
                  Restrictions whose polygon centroid falls outside are excluded.

        Returns:
            List of ``AirspaceRestriction`` objects.
        """
        features = self._fetch_features()
        restrictions: list[AirspaceRestriction] = []
        for feat in features:
            props = feat.get("properties", {})
            notam_type = (
                props.get("type") or props.get("classification") or ""
            ).upper()
            if notam_type in {"TFR", "MOA", "NFZ", "ADIZ", "CTR", "P", "R"}:
                try:
                    restrictions.append(faa_notam_to_restriction(feat))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("FaaNotamConnector: skipping restriction — %s", exc)

        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            filtered: list[AirspaceRestriction] = []
            for r in restrictions:
                coords = r.geometry_geojson.get("coordinates", [[]])[0]
                if not coords:
                    continue
                clon = sum(c[0] for c in coords) / len(coords)
                clat = sum(c[1] for c in coords) / len(coords)
                if min_lon <= clon <= max_lon and min_lat <= clat <= max_lat:
                    filtered.append(r)
            return filtered

        return restrictions

    def fetch_notams(self, icao_code: str | None = None) -> list[NotamEvent]:
        """Fetch NOTAMs from the FAA API.

        Args:
            icao_code: Optional ICAO 4-letter location (case-insensitive).
                       When provided, only matching NOTAMs are returned.

        Returns:
            List of ``NotamEvent`` objects.
        """
        locations = (
            [icao_code.upper()] if icao_code else self._icao_locations
        )
        notams: list[NotamEvent] = []
        seen: set[str] = set()
        for icao in locations:
            raw_features = self._fetch_for_icao(icao)
            for feat in raw_features:
                props = feat.get("properties", {})
                notam_type = (
                    props.get("type") or props.get("classification") or ""
                ).upper()
                if notam_type in {"TFR", "MOA", "NFZ", "ADIZ", "CTR", "P", "R"}:
                    continue  # restriction, not a plain NOTAM
                notam_number = props.get("notamNumber") or props.get("notam_number") or ""
                if notam_number in seen:
                    continue
                seen.add(notam_number)
                try:
                    notams.append(faa_notam_to_notam(feat))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("FaaNotamConnector: skipping NOTAM — %s", exc)
        return notams

    # ── Internals ─────────────────────────────────────────────────────────

    def _fetch_features(self) -> list[dict[str, Any]]:
        """Fetch GeoJSON features for all configured ICAO locations."""
        features: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for icao in self._icao_locations:
            for feat in self._fetch_for_icao(icao):
                props = feat.get("properties", {})
                uid = props.get("notamNumber") or id(feat)
                if uid not in seen_ids:
                    seen_ids.add(str(uid))
                    features.append(feat)
        self._last_poll = datetime.now(UTC)
        return features

    def _fetch_for_icao(self, icao: str) -> list[dict[str, Any]]:
        """Fetch raw GeoJSON features for a single ICAO location code."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    _BASE_URL,
                    headers={"client_id": self._client_id},
                    params={
                        "icaoLocation": icao,
                        "responseFormat": "geoJson",
                    },
                )
                resp.raise_for_status()
            data = resp.json()
            # FAA API returns {"features": [...]} or a FeatureCollection
            if isinstance(data, dict):
                features = data.get("features") or data.get("items") or []
                if not features and data.get("type") == "Feature":
                    features = [data]
            elif isinstance(data, list):
                features = data
            else:
                features = []
            self._error_count = max(0, self._error_count - 1)
            return features
        except httpx.HTTPStatusError as exc:
            self._error_count += 1
            logger.warning(
                "FaaNotamConnector: HTTP %d for ICAO %s — %s",
                exc.response.status_code,
                icao,
                exc,
            )
            raise ConnectorError(
                f"FAA NOTAM API HTTP {exc.response.status_code} for {icao}"
            ) from exc
        except httpx.RequestError as exc:
            self._error_count += 1
            logger.warning("FaaNotamConnector: request error for ICAO %s — %s", icao, exc)
            raise ConnectorError(f"FAA NOTAM API unreachable: {exc}") from exc
