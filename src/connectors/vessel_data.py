"""VesselData RapidAPI connector (vessel-data.p.rapidapi.com).

Fetches vessel positions using a centre+radius area query.
The centre is derived from the midpoint of the configured bounding box.

connector_id:  ``vessel-data``
source_type:   ``telemetry``

Configure via environment variables:
  VESSEL_DATA_API_KEY    — RapidAPI subscription key (required)
  VESSEL_DATA_SOUTH/WEST/NORTH/EAST — default bounding box
  VESSEL_DATA_POLL_INTERVAL — polling interval in seconds
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

_HOST = "vessel-data.p.rapidapi.com"
_VESSELS_URL = f"https://{_HOST}/vessels"
_HEALTH_URL = f"https://{_HOST}"

_LICENSE = LicenseRecord(
    access_tier="commercial",
    commercial_use="check-provider-terms",
    redistribution="not-allowed",
    attribution_required=True,
)


def _bbox_to_center_radius(
    south: float, west: float, north: float, east: float
) -> Tuple[float, float, float]:
    """Return (center_lat, center_lon, radius_km) for a bounding box."""
    center_lat = (south + north) / 2.0
    center_lon = (west + east) / 2.0
    # Radius = half the diagonal distance of the bbox
    r = 6371.0
    dlat = math.radians(north - south)
    dlon = math.radians(east - west)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(south)) * math.cos(math.radians(north))
        * math.sin(dlon / 2) ** 2
    )
    diagonal_km = 2 * r * math.asin(math.sqrt(a))
    return center_lat, center_lon, round(diagonal_km / 2, 1)


class VesselDataConnector(BaseConnector):
    """Vessel Data API connector using centre+radius area queries.

    Converts the bounding box into a centre lat/lon + radius (km) and
    queries the VesselData endpoint.  Normalises results into
    ship_position CanonicalEvents.

    Args:
        api_key:  RapidAPI subscription key for vessel-data.p.rapidapi.com.
        south/west/north/east: Default bounding box (Strait of Hormuz by default).
        timeout:  HTTP request timeout in seconds.
    """

    connector_id = "vessel-data"
    display_name = "VesselData Maritime Positions"
    source_type = SourceType.TELEMETRY.value

    def __init__(
        self,
        api_key: str = "",
        south: float = 24.5,
        west: float = 55.5,
        north: float = 27.5,
        east: float = 60.5,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._default_bbox = (south, west, north, east)
        self._timeout = timeout

    def connect(self) -> None:
        if not self._api_key:
            raise ConnectorUnavailableError(
                "VESSEL_DATA_API_KEY is not set — VesselData connector disabled"
            )

    def fetch(
        self,
        geometry: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch vessels near the centre of the given geometry / default bbox."""
        south, west, north, east = self._resolve_bbox(geometry)
        lat, lon, radius_km = _bbox_to_center_radius(south, west, north, east)

        headers = {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": _HOST,
        }
        params: Dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "radius": radius_km,
        }
        try:
            resp = httpx.get(
                _VESSELS_URL, headers=headers, params=params, timeout=self._timeout
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorUnavailableError(
                f"VesselData HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise ConnectorUnavailableError(f"VesselData request failed: {exc}") from exc

        data = resp.json()
        # Response may be a list or a dict with a data/vessels key
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "vessels", "result", "results", "features"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        log.warning("vessel-data: unexpected response shape — returning empty list")
        return []

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:  # noqa: PLR0912
        """Convert a single vessel record into a ship_position CanonicalEvent."""
        try:
            lat = float(
                raw.get("lat") or raw.get("latitude") or raw.get("LAT") or 0
            )
            lon = float(
                raw.get("lon") or raw.get("longitude") or raw.get("LON") or 0
            )
        except (TypeError, ValueError) as exc:
            raise NormalizationError(f"vessel-data: bad lat/lon in {raw!r}") from exc

        if lat == 0.0 and lon == 0.0:
            raise NormalizationError("vessel-data: null-island position discarded")

        mmsi = str(raw.get("mmsi") or raw.get("MMSI") or "")
        name = str(
            raw.get("name")
            or raw.get("vesselName")
            or raw.get("vessel_name")
            or raw.get("NAME")
            or ""
        )
        speed = float(raw.get("speed") or raw.get("sog") or raw.get("SPEED") or 0)
        heading = float(raw.get("heading") or raw.get("hdg") or raw.get("HEADING") or 0)
        course = float(raw.get("course") or raw.get("cog") or raw.get("COURSE") or heading)
        nav_status = int(raw.get("status") or raw.get("navStatus") or raw.get("STATUS") or 0)
        imo = str(raw.get("imo") or raw.get("IMO") or "")
        vessel_type = str(raw.get("type") or raw.get("typeName") or raw.get("vessel_type") or "")
        flag = str(raw.get("flag") or raw.get("country") or raw.get("FLAG") or "")

        ts_raw = (
            raw.get("timestamp")
            or raw.get("lastUpdate")
            or raw.get("time")
            or raw.get("TIMESTAMP")
        )
        try:
            if isinstance(ts_raw, (int, float)):
                event_time = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            elif isinstance(ts_raw, str):
                event_time = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            else:
                event_time = datetime.now(timezone.utc)
        except (ValueError, OSError):
            event_time = datetime.now(timezone.utc)

        event_id = make_event_id("vessel-data", mmsi or f"{lat},{lon}", event_time.isoformat())
        geometry_out = {"type": "Point", "coordinates": [lon, lat]}

        attrs = ShipPositionAttributes(
            mmsi=mmsi or None,
            imo=imo or None,
            vessel_name=name or None,
            speed_kn=speed if speed >= 0 else None,
            heading_deg=heading if heading >= 0 else None,
            course_deg=course if course >= 0 else None,
            nav_status=str(nav_status) if nav_status else None,
        )
        attrs_dict = attrs.model_dump(exclude_none=True)
        if flag:
            attrs_dict["flag"] = flag

        return CanonicalEvent(
            event_id=event_id,
            source="vessel-data",
            source_type=SourceType.TELEMETRY,
            entity_type=EntityType.VESSEL,
            entity_id=mmsi or event_id,
            event_type=EventType.SHIP_POSITION,
            event_time=event_time,
            geometry=geometry_out,
            centroid=geometry_out,
            confidence=0.88,
            attributes=attrs_dict,
            normalization=NormalizationRecord(normalized_by="connector.vessel-data"),
            provenance=ProvenanceRecord(
                raw_source_ref=f"rapidapi://{_HOST}/vessels"
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
                log.debug("vessel-data normalize skip: %s", exc)
        return events

    def health(self) -> ConnectorHealthStatus:
        healthy = bool(self._api_key)
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=healthy,
            message="API key present" if healthy else "VESSEL_DATA_API_KEY not configured",
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def _resolve_bbox(
        self, geometry: Optional[Dict[str, Any]]
    ) -> Tuple[float, float, float, float]:
        """Return (south, west, north, east) from GeoJSON or default bbox."""
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
