"""OpenSky Network aviation connector — P3-2.

Implements BaseConnector backed by the OpenSky Network REST API.

P3-2.1: OpenSkyConnector — polling REST connector for aircraft state vectors.
P3-2.2: AOI-bounded queries via bounding-box filter.
P3-2.3: Normalise state vectors → aircraft_position canonical events.
P3-2.4: Aircraft track segment builder.
P3-2.5: Polling scheduler (Celery beat task wired in app/workers/tasks.py).

connector_id:  ``opensky``
source_type:   ``telemetry``

API: https://opensky-network.org/apidoc/rest.html
Rate limits (anonymous): 10 req/10 min, max look-back 1 hour.
Rate limits (registered): higher limits with credentials.

NON-COMMERCIAL note: OpenSky data is provided for non-commercial research and
academic use.  Commercial use requires a separate agreement.  This is recorded
in the license field of every canonical event produced by this connector.

Configure via environment variables:
  OPENSKY_USERNAME  (optional — increases rate limits)
  OPENSKY_PASSWORD  (optional)
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
    AircraftAttributes,
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

log = logging.getLogger(__name__)

_API_BASE = "https://opensky-network.org/api"
_STATES_ENDPOINT = f"{_API_BASE}/states/all"

# Non-commercial license record — enforce from day 1.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="not-allowed",
    redistribution="check-provider-terms",
    attribution_required=True,
)

# OpenSky state vector column indices (0-based)
# https://opensky-network.org/apidoc/rest.html#response
_COL = {
    "icao24": 0,
    "callsign": 1,
    "origin_country": 2,
    "time_position": 3,
    "last_contact": 4,
    "longitude": 5,
    "latitude": 6,
    "baro_altitude": 7,
    "on_ground": 8,
    "velocity": 9,
    "true_track": 10,
    "vertical_rate": 11,
    "sensors": 12,
    "geo_altitude": 13,
    "squawk": 14,
    "spi": 15,
    "position_source": 16,
}


def _bbox_from_geojson(geometry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Derive (min_lat, min_lon, max_lat, max_lon) from a GeoJSON geometry."""
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
        raise ValueError(f"Unsupported geometry type: {gtype!r}")
    lons = [c[0] for c in coords_flat]
    lats = [c[1] for c in coords_flat]
    return min(lats), min(lons), max(lats), max(lons)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _track_segment_from_positions(
    positions: List[CanonicalEvent],
    entity_id: str,
) -> Optional[CanonicalEvent]:
    """Aggregate aircraft_position events into an aircraft_track_segment."""
    if len(positions) < 2:
        return None

    first = positions[0]
    last = positions[-1]

    total_dist_km = 0.0
    for i in range(len(positions) - 1):
        c0 = positions[i].centroid["coordinates"]
        c1 = positions[i + 1].centroid["coordinates"]
        total_dist_km += _haversine_km(c0[1], c0[0], c1[1], c1[0])

    duration_s = max((last.event_time - first.event_time).total_seconds(), 1)

    seg_id = make_event_id("opensky", f"track:{entity_id}", first.event_time.isoformat())
    line_coords = [p.centroid["coordinates"] for p in positions]
    geom = {"type": "LineString", "coordinates": line_coords}
    centroid = positions[len(positions) // 2].centroid

    return CanonicalEvent(
        event_id=seg_id,
        source="opensky",
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.TRACK,
        entity_id=entity_id,
        event_type=EventType.AIRCRAFT_TRACK_SEGMENT,
        event_time=first.event_time,
        time_start=first.event_time,
        time_end=last.event_time,
        geometry=geom,
        centroid=centroid,
        confidence=0.9,
        attributes={
            "icao24": entity_id,
            "callsign": first.attributes.get("callsign", ""),
            "total_distance_km": round(total_dist_km, 3),
            "duration_s": duration_s,
            "position_count": len(positions),
        },
        normalization=NormalizationRecord(normalized_by="connector.opensky"),
        provenance=ProvenanceRecord(raw_source_ref=f"opensky://icao24/{entity_id}/track@{first.event_time.isoformat()}"),
        license=_LICENSE,
        correlation_keys=CorrelationKeys(icao24=entity_id),
    )


class OpenSkyConnector(BaseConnector):
    """OpenSky Network aircraft state vector connector.

    Args:
        username: Optional OpenSky registered username (increases rate limits).
        password: Optional password for the above username.
        base_url: Override for the API base URL (useful for testing).
    """

    connector_id = "opensky"
    display_name = "OpenSky Network Aircraft Positions"
    source_type = SourceType.TELEMETRY.value

    def __init__(
        self,
        username: str = "",
        password: str = "",
        base_url: str = _API_BASE,
    ) -> None:
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password) if username else None
        self._connected: bool = False

    def connect(self) -> None:
        """Probe the OpenSky API; no persistent connection required."""
        try:
            resp = httpx.get(
                f"{self._base_url}/states/all",
                params={"lamin": 24.0, "lomin": 46.0, "lamax": 24.5, "lomax": 46.5},
                auth=self._auth,  # type: ignore[arg-type]
                timeout=10.0,
            )
            if resp.status_code == 401:
                raise ConnectorUnavailableError(
                    "OpenSky: authentication failed (check OPENSKY_USERNAME/PASSWORD)"
                )
            if resp.status_code >= 500:
                raise ConnectorUnavailableError(
                    f"OpenSky API unavailable: HTTP {resp.status_code}"
                )
            self._connected = True
            log.info("OpenSkyConnector: connected (HTTP %s)", resp.status_code)
        except ConnectorUnavailableError:
            raise
        except Exception as exc:
            raise ConnectorUnavailableError(f"OpenSky connectivity check failed: {exc}") from exc

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch aircraft state vectors for the given AOI bounding box.

        Args:
            geometry: GeoJSON geometry dict (Polygon or MultiPolygon) for the AOI.
            start_time: Ignored (OpenSky returns current state only for free tier).
            end_time:   Ignored (see above).

        Returns:
            List of raw state vector dicts, one per aircraft observed in the bbox.
        """
        min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(geometry)
        params = {
            "lamin": min_lat,
            "lomin": min_lon,
            "lamax": max_lat,
            "lomax": max_lon,
        }
        try:
            resp = httpx.get(
                f"{self._base_url}/states/all",
                params=params,
                auth=self._auth,  # type: ignore[arg-type]
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            states = data.get("states") or []
            log.info(
                "OpenSkyConnector.fetch: %d aircraft in bbox (%s, %s, %s, %s)",
                len(states),
                min_lat,
                min_lon,
                max_lat,
                max_lon,
            )
            fetched_at = datetime.now(timezone.utc).isoformat()
            return [
                {"_state": sv, "_fetched_at": fetched_at, "_bbox": params}
                for sv in states
            ]
        except ConnectorUnavailableError:
            raise
        except Exception as exc:
            log.warning("OpenSkyConnector.fetch failed: %s", exc)
            return []

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Normalize a single OpenSky state-vector dict → aircraft_position CanonicalEvent.

        Raises:
            NormalizationError: If required fields are missing or invalid.
        """
        try:
            sv: List[Any] = raw["_state"]
            fetched_at_str: str = raw.get("_fetched_at", datetime.now(timezone.utc).isoformat())
            fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))

            icao24 = str(sv[_COL["icao24"]] or "").strip().lower()
            if not icao24:
                raise NormalizationError("State vector missing icao24")

            lon = sv[_COL["longitude"]]
            lat = sv[_COL["latitude"]]
            if lon is None or lat is None:
                raise NormalizationError(f"icao24 {icao24}: no position data")

            lon = float(lon)
            lat = float(lat)
            if lon == 0.0 and lat == 0.0:
                raise NormalizationError(f"icao24 {icao24}: null-island position discarded")

            # Timestamp
            time_position = sv[_COL["time_position"]]
            if time_position:
                event_time = datetime.fromtimestamp(int(time_position), tz=timezone.utc)
            else:
                event_time = fetched_at

            callsign = (sv[_COL["callsign"]] or "").strip() or None
            origin_country = sv[_COL["origin_country"]] or None
            baro_alt = sv[_COL["baro_altitude"]]
            geo_alt = sv[_COL["geo_altitude"]]
            velocity = sv[_COL["velocity"]]
            true_track = sv[_COL["true_track"]]
            vertical_rate = sv[_COL["vertical_rate"]]
            on_ground = sv[_COL["on_ground"]]
            squawk = sv[_COL["squawk"]]

            event_id = make_event_id("opensky", icao24, event_time.isoformat())
            geometry = {"type": "Point", "coordinates": [lon, lat]}

            attribs = AircraftAttributes(
                icao24=icao24,
                callsign=callsign,
                origin_country=origin_country,
                baro_altitude_m=float(baro_alt) if baro_alt is not None else None,
                geo_altitude_m=float(geo_alt) if geo_alt is not None else None,
                velocity_ms=float(velocity) if velocity is not None else None,
                true_track_deg=float(true_track) if true_track is not None else None,
                vertical_rate_ms=float(vertical_rate) if vertical_rate is not None else None,
                on_ground=bool(on_ground) if on_ground is not None else None,
                squawk=str(squawk) if squawk else None,
            )

            return CanonicalEvent(
                event_id=event_id,
                source="opensky",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.AIRCRAFT,
                entity_id=icao24,
                event_type=EventType.AIRCRAFT_POSITION,
                event_time=event_time,
                ingested_at=fetched_at,
                geometry=geometry,
                centroid=geometry,
                confidence=0.90,
                attributes=attribs.model_dump(exclude_none=True),
                normalization=NormalizationRecord(normalized_by="connector.opensky"),
                provenance=ProvenanceRecord(
                    raw_source_ref=f"opensky://icao24/{icao24}@{event_time.isoformat()}",
                    source_record_id=icao24,
                ),
                license=_LICENSE,
                correlation_keys=CorrelationKeys(icao24=icao24, callsign=callsign),
            )
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(f"OpenSky normalization failed: {exc}") from exc

    def normalize_all(self, records: List[Dict[str, Any]]) -> List[CanonicalEvent]:
        """Normalize a batch of state-vector dicts, skipping failures."""
        events: List[CanonicalEvent] = []
        for r in records:
            try:
                events.append(self.normalize(r))
            except NormalizationError as exc:
                log.debug("OpenSky normalization skipped: %s", exc)
        return events

    def build_track_segments(
        self,
        events: List[CanonicalEvent],
        min_positions: int = 2,
    ) -> List[CanonicalEvent]:
        """P3-2.4: Group aircraft_position events by icao24 and build track segments.

        Args:
            events: List of aircraft_position CanonicalEvents.
            min_positions: Minimum positions to form a segment.

        Returns:
            List of aircraft_track_segment CanonicalEvents, one per icao24.
        """
        by_icao: Dict[str, List[CanonicalEvent]] = {}
        for e in events:
            if e.event_type != EventType.AIRCRAFT_POSITION:
                continue
            icao = e.attributes.get("icao24", "unknown")
            by_icao.setdefault(icao, []).append(e)

        segments: List[CanonicalEvent] = []
        for icao, positions in by_icao.items():
            positions.sort(key=lambda e: e.event_time)
            if len(positions) < min_positions:
                continue
            seg = _track_segment_from_positions(positions, icao)
            if seg:
                segments.append(seg)

        log.info(
            "OpenSkyConnector.build_track_segments: %d icao24s → %d segments",
            len(by_icao),
            len(segments),
        )
        return segments

    def health(self) -> ConnectorHealthStatus:
        """Lightweight GET to the OpenSky API states endpoint."""
        try:
            resp = httpx.get(
                f"{self._base_url}/states/all",
                params={"lamin": 24.0, "lomin": 46.0, "lamax": 24.1, "lomax": 46.1},
                auth=self._auth,  # type: ignore[arg-type]
                timeout=5.0,
            )
            ok = resp.status_code < 500
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=ok,
                message=f"HTTP {resp.status_code}",
                last_successful_poll=datetime.now(timezone.utc) if ok else None,
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
