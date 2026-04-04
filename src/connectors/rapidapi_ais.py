"""RapidAPI maritime AIS connector.

Fetches vessel positions from a configurable RapidAPI maritime endpoint using
a bounding-box area filter.  The API host is set via RAPID_API_HOST so the
same connector works with any bbox-capable RapidAPI AIS provider.

Default host: ``ais-hub.p.rapidapi.com``

connector_id:  ``rapidapi-ais``
source_type:   ``telemetry``

Configure via environment variables:
  RAPID_API_KEY          — RapidAPI subscription key (required)
  RAPID_API_HOST         — RapidAPI X-RapidAPI-Host header value
  RAPID_API_SOUTH/WEST/NORTH/EAST — default bounding box
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    ConnectorUnavailableError,
    NormalizationError,
)
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    ShipPositionAttributes,
    SourceType,
    make_event_id,
)

log = logging.getLogger(__name__)

_DEFAULT_HOST = "ais-hub.p.rapidapi.com"
_BASE_URL_TPL = "https://{host}/vessels"
_HEALTH_URL = "https://rapidapi.com"

_LICENSE = LicenseRecord(
    access_tier="commercial",
    commercial_use="check-provider-terms",
    redistribution="not-allowed",
    attribution_required=True,
)


def _bbox_from_coords(
    south: float, west: float, north: float, east: float
) -> Tuple[float, float, float, float]:
    return south, west, north, east


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


class RapidApiAisConnector(BaseConnector):
    """Maritime AIS connector backed by a bbox-capable RapidAPI endpoint.

    Ships a bounded spatial search request and normalises the response into
    ship_position CanonicalEvents.  The connector is stateless: each fetch()
    call is a self-contained HTTP GET.

    Args:
        api_key:  RapidAPI subscription key.
        host:     RapidAPI host header (X-RapidAPI-Host).
        south/west/north/east: Default bounding box when no geometry is passed.
    """

    connector_id = "rapidapi-ais"
    display_name = "RapidAPI AIS Maritime Positions"
    source_type = SourceType.TELEMETRY.value

    def __init__(
        self,
        api_key: str = "",
        host: str = _DEFAULT_HOST,
        south: float = 24.5,
        west: float = 55.5,
        north: float = 27.5,
        east: float = 60.5,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._host = host
        self._default_bbox = (south, west, north, east)
        self._timeout = timeout
        self._url = _BASE_URL_TPL.format(host=host)

    def connect(self) -> None:
        if not self._api_key:
            raise ConnectorUnavailableError(
                "RAPID_API_KEY is not set — RapidAPI AIS connector disabled"
            )

    def fetch(
        self,
        geometry: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch vessel positions for the given geometry or default bbox."""
        south, west, north, east = self._resolve_bbox(geometry)
        headers = {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self._host,
        }
        params: Dict[str, Any] = {
            "south": south,
            "west": west,
            "north": north,
            "east": east,
        }
        try:
            resp = httpx.get(
                self._url, headers=headers, params=params, timeout=self._timeout
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorUnavailableError(
                f"RapidAPI AIS HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise ConnectorUnavailableError(f"RapidAPI AIS request failed: {exc}") from exc

        data = resp.json()
        # Normalise response: accept list or {data: [...]} envelope
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "vessels", "results", "features"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        log.warning("rapidapi-ais: unexpected response shape — returning empty list")
        return []

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:  # noqa: PLR0912
        """Convert a single vessel record into a ship_position CanonicalEvent."""
        try:
            lat = float(raw.get("lat") or raw.get("latitude") or 0)
            lon = float(raw.get("lon") or raw.get("longitude") or 0)
        except (TypeError, ValueError) as exc:
            raise NormalizationError(f"rapidapi-ais: bad lat/lon in {raw!r}") from exc

        # Discard null-island / absent positions
        if lat == 0.0 and lon == 0.0:
            raise NormalizationError("rapidapi-ais: null-island position discarded")

        mmsi = str(raw.get("mmsi") or raw.get("MMSI") or "")
        name = str(raw.get("name") or raw.get("vesselName") or raw.get("shipname") or "")
        speed = float(raw.get("speed") or raw.get("sog") or 0)
        heading = float(raw.get("heading") or raw.get("hdg") or 0)
        course = float(raw.get("course") or raw.get("cog") or heading)
        nav_status = int(raw.get("status") or raw.get("navStatus") or 0)

        # Timestamp
        ts_raw = raw.get("timestamp") or raw.get("time") or raw.get("lastUpdate")
        try:
            if isinstance(ts_raw, (int, float)):
                event_time = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            elif isinstance(ts_raw, str):
                event_time = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            else:
                event_time = datetime.now(timezone.utc)
        except (ValueError, OSError):
            event_time = datetime.now(timezone.utc)

        event_id = make_event_id("rapidapi-ais", mmsi or f"{lat},{lon}", event_time.isoformat())
        geometry = {"type": "Point", "coordinates": [lon, lat]}

        return CanonicalEvent(
            event_id=event_id,
            source="rapidapi-ais",
            source_type=SourceType.TELEMETRY,
            entity_type=EntityType.VESSEL,
            entity_id=mmsi or event_id,
            event_type=EventType.SHIP_POSITION,
            event_time=event_time,
            geometry=geometry,
            centroid=geometry,
            confidence=0.85,
            attributes=ShipPositionAttributes(
                mmsi=mmsi or None,
                vessel_name=name or None,
                speed_kn=speed if speed >= 0 else None,
                heading_deg=heading if heading >= 0 else None,
                course_deg=course if course >= 0 else None,
                nav_status=str(raw.get("statusText") or nav_status or "") or None,
            ).model_dump(exclude_none=True),
            normalization=NormalizationRecord(normalized_by="connector.rapidapi-ais"),
            provenance=ProvenanceRecord(
                raw_source_ref=f"rapidapi://{self._host}/vessels"
            ),
            license=_LICENSE,
            correlation_keys=CorrelationKeys(mmsi=mmsi),
        )

    def normalize_all(self, raw_list: List[Dict[str, Any]]) -> List[CanonicalEvent]:
        events: List[CanonicalEvent] = []
        for record in raw_list:
            try:
                events.append(self.normalize(record))
            except NormalizationError as exc:
                log.debug("rapidapi-ais normalize skip: %s", exc)
        return events

    def health(self) -> ConnectorHealthStatus:
        healthy = bool(self._api_key)
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=healthy,
            message="API key present" if healthy else "RAPID_API_KEY not configured",
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def _resolve_bbox(
        self, geometry: Optional[Dict[str, Any]]
    ) -> Tuple[float, float, float, float]:
        """Return bbox from GeoJSON geometry, or fall back to default bbox."""
        if not geometry:
            return self._default_bbox
        gtype = geometry.get("type", "")
        coords_flat: List[List[float]] = []
        if gtype == "Point":
            coords_flat = [geometry["coordinates"]]
        elif gtype == "Polygon":
            coords_flat = geometry["coordinates"][0]
        elif gtype == "MultiPolygon":
            for poly in geometry["coordinates"]:
                coords_flat.extend(poly[0])
        else:
            return self._default_bbox
        lons = [c[0] for c in coords_flat]
        lats = [c[1] for c in coords_flat]
        return min(lats), min(lons), max(lats), max(lons)
