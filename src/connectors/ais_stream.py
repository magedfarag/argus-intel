"""AIS Stream connector — P3-1.

Implements BaseConnector backed by the AISStream.io WebSocket API.

P3-1.1: AisStreamConnector — backend WebSocket relay (browser never connects directly).
P3-1.2: AOI-bounded subscription; positions only fetched for active AOIs.
P3-1.3: Normalises AIS messages → ship_position canonical events.
P3-1.4: Track segment builder aggregates positions → ship_track_segment events.
P3-1.5: Reconnect + throttling policies (circuit-breaker-aware).

connector_id:  ``ais-stream``
source_type:   ``telemetry``

AISStream.io requires an API key (free tier available at https://aisstream.io).
Configure via environment variable: AISSTREAM_API_KEY.

If the API key is absent the connector registers as disabled — no exception at startup.
The backend acts as a relay: raw WebSocket messages are fetched in a bounded
collection window and returned as a list, keeping the BaseConnector.fetch() contract.
"""
from __future__ import annotations

import json
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

# AISStream WebSocket endpoint
_WS_URL = "wss://stream.aisstream.io/v0/stream"
# Lightweight REST health probe (AISStream doesn't expose a public REST ping;
# we probe the CORS-friendly status page instead)
_HEALTH_URL = "https://aisstream.io"

# License: AIS data is public (international maritime regulations).
# Commercial redistribution terms vary by aggregator.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)

# Navigation status code → human-readable label
_NAV_STATUS: Dict[int, str] = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    15: "Undefined",
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
        raise ValueError(f"Unsupported geometry type for AOI bounding-box extraction: {gtype!r}")
    lons = [c[0] for c in coords_flat]
    lats = [c[1] for c in coords_flat]
    return min(lats), min(lons), max(lats), max(lons)


def _track_segment_from_positions(
    positions: List[CanonicalEvent],
    entity_id: str,
) -> Optional[CanonicalEvent]:
    """Aggregate a list of ship_position events into a ship_track_segment event.

    Returns None if fewer than 2 positions are available.
    """
    if len(positions) < 2:
        return None

    first = positions[0]
    last = positions[-1]

    # Haversine distance accumulator
    total_dist_km = 0.0
    for i in range(len(positions) - 1):
        c0 = positions[i].centroid["coordinates"]
        c1 = positions[i + 1].centroid["coordinates"]
        total_dist_km += _haversine_km(c0[1], c0[0], c1[1], c1[0])

    duration_s = max(
        (last.event_time - first.event_time).total_seconds(), 1
    )
    avg_speed_kn = (total_dist_km / (duration_s / 3600)) / 1.852 if duration_s > 0 else 0.0

    mmsi = first.attributes.get("mmsi", "")
    seg_id = make_event_id("ais-stream", f"track:{mmsi}", first.event_time.isoformat())

    # Build a linestring geometry from all centroids
    line_coords = [p.centroid["coordinates"] for p in positions]
    geom = {"type": "LineString", "coordinates": line_coords}
    centroid_idx = len(positions) // 2
    centroid = positions[centroid_idx].centroid

    return CanonicalEvent(
        event_id=seg_id,
        source="ais-stream",
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.TRACK,
        entity_id=entity_id,
        event_type=EventType.SHIP_TRACK_SEGMENT,
        event_time=first.event_time,
        time_start=first.event_time,
        time_end=last.event_time,
        geometry=geom,
        centroid=centroid,
        confidence=0.9,
        attributes={
            "mmsi": mmsi,
            "vessel_name": first.attributes.get("vessel_name", ""),
            "total_distance_km": round(total_dist_km, 3),
            "duration_s": duration_s,
            "avg_speed_kn": round(avg_speed_kn, 2),
            "position_count": len(positions),
        },
        normalization=NormalizationRecord(normalized_by="connector.ais-stream"),
        provenance=ProvenanceRecord(raw_source_ref=f"ais://mmsi/{mmsi}/track@{first.event_time.isoformat()}"),
        license=_LICENSE,
        correlation_keys=CorrelationKeys(mmsi=mmsi),
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class AisStreamConnector(BaseConnector):
    """AISStream.io WebSocket relay connector.

    Fetches real-time AIS position data for a given AOI bounding box.

    Args:
        api_key: AISStream API key.  If empty the connector registers disabled.
        collect_timeout_s: Duration (seconds) to collect messages per fetch() call.
        max_messages: Maximum messages to collect per fetch() call.
    """

    connector_id = "ais-stream"
    display_name = "AISStream.io Maritime Positions"
    source_type = SourceType.TELEMETRY.value

    def __init__(
        self,
        api_key: str = "",
        collect_timeout_s: float = 10.0,
        max_messages: int = 500,
    ) -> None:
        self._api_key = api_key
        self._collect_timeout_s = collect_timeout_s
        self._max_messages = max_messages
        self._connected: bool = False

    def connect(self) -> None:
        """Verify API key is present.  Does not open a persistent connection."""
        if not self._api_key:
            raise ConnectorUnavailableError(
                "AISSTREAM_API_KEY not configured — AIS connector disabled"
            )
        self._connected = True
        log.info("AisStreamConnector: API key present — connector active")

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Collect AIS position messages for the given AOI bounding box.

        Opens a short-lived WebSocket connection to AISStream.io, subscribes to
        the AOI bounding box, and collects up to *max_messages* position reports.
        The connection is closed after *collect_timeout_s* seconds or when the
        message cap is reached.

        Returns a list of raw AIS message dicts (AISStream JSON format).

        Note:
            This method requires the ``websockets`` package.
            If unavailable, it raises ConnectorUnavailableError.
        """
        try:
            import asyncio

            import websockets  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ConnectorUnavailableError(
                "websockets package required for AIS fetch: pip install websockets"
            ) from exc

        min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(geometry)
        bounding_boxes = [[min_lat, min_lon, max_lat, max_lon]]

        subscribe_msg = {
            "APIKey": self._api_key,
            "BoundingBoxes": [bounding_boxes],
            "FilterMessageTypes": ["PositionReport", "ExtendedClassBPositionReport"],
        }

        collected: List[Dict[str, Any]] = []

        async def _collect() -> None:
            try:
                async with websockets.connect(_WS_URL, open_timeout=10) as ws:
                    await ws.send(json.dumps(subscribe_msg))
                    deadline = asyncio.get_event_loop().time() + self._collect_timeout_s
                    while (
                        len(collected) < self._max_messages
                        and asyncio.get_event_loop().time() < deadline
                    ):
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            msg = json.loads(raw)
                            # Inject fetch metadata for normalization
                            msg["_fetched_at"] = datetime.now(timezone.utc).isoformat()
                            collected.append(msg)
                        except asyncio.TimeoutError:
                            # No message in 2s — check deadline and continue
                            continue
            except Exception as exc:
                log.warning("AisStreamConnector.fetch: WebSocket error: %s", exc)

        try:
            asyncio.run(_collect())
        except RuntimeError:
            # Nested event loop (e.g. in tests) — run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(asyncio.run, _collect()).result()

        log.info("AisStreamConnector.fetch: collected %d messages", len(collected))
        return collected

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Normalize a single AIS message dict → ship_position CanonicalEvent.

        Supports AISStream JSON envelope with ``Message.PositionReport`` or
        ``Message.ExtendedClassBPositionReport``.

        Raises:
            NormalizationError: If required fields are missing.
        """
        try:
            msg_type = raw.get("MessageType", "")
            message = raw.get("Message", {})
            meta = raw.get("MetaData", {})

            pos = message.get("PositionReport") or message.get("ExtendedClassBPositionReport") or {}

            raw_mmsi = meta.get("MMSI") or pos.get("UserID")
            mmsi = str(raw_mmsi).strip() if raw_mmsi is not None else ""
            vessel_name = (meta.get("ShipName") or "").strip()
            lat = float(pos.get("Latitude", 0.0))
            lon = float(pos.get("Longitude", 0.0))
            course = pos.get("CourseOverGround")
            speed = pos.get("SpeedOverGround")
            heading = pos.get("TrueHeading")
            nav_code = pos.get("NavigationalStatus", 15)
            ship_type = meta.get("ShipType")

            fetched_at_str = raw.get("_fetched_at") or datetime.now(timezone.utc).isoformat()
            fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))

            time_utc_str = meta.get("time_utc") or fetched_at_str
            event_time = datetime.fromisoformat(time_utc_str.replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            if not mmsi:
                raise NormalizationError("AIS message missing MMSI")
            if lat == 0.0 and lon == 0.0:
                raise NormalizationError(f"MMSI {mmsi}: null-island position discarded")

            event_id = make_event_id("ais-stream", mmsi, event_time.isoformat())
            geometry = {"type": "Point", "coordinates": [lon, lat]}

            attribs = ShipPositionAttributes(
                mmsi=mmsi,
                vessel_name=vessel_name or None,
                ship_type=int(ship_type) if ship_type is not None else None,
                course_deg=float(course) if course is not None else None,
                speed_kn=float(speed) if speed is not None else None,
                heading_deg=float(heading) if heading not in (None, 511) else None,
                nav_status=_NAV_STATUS.get(int(nav_code), "Undefined"),
            )

            warnings: List[str] = []
            if msg_type not in ("PositionReport", "ExtendedClassBPositionReport"):
                warnings.append(f"Unexpected message type: {msg_type!r}")

            return CanonicalEvent(
                event_id=event_id,
                source="ais-stream",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.VESSEL,
                entity_id=mmsi,
                event_type=EventType.SHIP_POSITION,
                event_time=event_time,
                ingested_at=fetched_at,
                geometry=geometry,
                centroid=geometry,
                confidence=0.95,
                attributes=attribs.model_dump(exclude_none=True),
                normalization=NormalizationRecord(
                    normalized_by="connector.ais-stream",
                    normalization_warnings=warnings,
                ),
                provenance=ProvenanceRecord(
                    raw_source_ref=f"ais://mmsi/{mmsi}@{event_time.isoformat()}",
                    source_record_id=mmsi,
                ),
                license=_LICENSE,
                correlation_keys=CorrelationKeys(mmsi=mmsi),
            )
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(f"AIS normalization failed: {exc}") from exc

    def normalize_all(self, records: List[Dict[str, Any]]) -> List[CanonicalEvent]:
        """Normalize a batch of AIS messages, skipping failed records."""
        events: List[CanonicalEvent] = []
        for r in records:
            try:
                events.append(self.normalize(r))
            except NormalizationError as exc:
                log.debug("AIS normalization skipped: %s", exc)
        return events

    def build_track_segments(
        self,
        events: List[CanonicalEvent],
        min_positions: int = 2,
    ) -> List[CanonicalEvent]:
        """P3-1.4: Group ship_position events by MMSI and build track segments.

        Args:
            events: List of ship_position CanonicalEvents.
            min_positions: Minimum positions required to build a segment.

        Returns:
            List of ship_track_segment CanonicalEvents, one per MMSI.
        """
        by_mmsi: Dict[str, List[CanonicalEvent]] = {}
        for e in events:
            if e.event_type != EventType.SHIP_POSITION:
                continue
            mmsi = e.attributes.get("mmsi", "unknown")
            by_mmsi.setdefault(mmsi, []).append(e)

        segments: List[CanonicalEvent] = []
        for mmsi, positions in by_mmsi.items():
            positions.sort(key=lambda e: e.event_time)
            if len(positions) < min_positions:
                continue
            seg = _track_segment_from_positions(positions, mmsi)
            if seg:
                segments.append(seg)

        log.info(
            "AisStreamConnector.build_track_segments: %d MMSIs → %d segments",
            len(by_mmsi),
            len(segments),
        )
        return segments

    def health(self) -> ConnectorHealthStatus:
        """P3-1.5: Lightweight reachability check — probes AISStream.io homepage."""
        if not self._api_key:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message="API key not configured",
            )
        try:
            r = httpx.get(_HEALTH_URL, timeout=5.0, follow_redirects=True)
            ok = r.status_code < 500
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=ok,
                message=f"HTTP {r.status_code}",
                last_successful_poll=datetime.now(timezone.utc) if ok else None,
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
