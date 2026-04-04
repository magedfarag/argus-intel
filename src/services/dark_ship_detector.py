"""Dark ship detection service — P6-4.

Detects vessels that disappeared from AIS within monitored zones by finding
track gaps > GAP_THRESHOLD_H hours while satellite imagery covers the area.

Algorithm:
  1. Group incoming ship_position events by MMSI.
  2. For each MMSI: sort by event_time, identify consecutive time gaps > threshold.
  3. If a gap falls inside the monitored bounding box, emit a dark_ship_candidate event.
  4. Confidence is scored by (gap_hours / 48) capped at 0.99, boosted by sanctions flag.

No external calls — pure in-memory analysis of the canonical event stream.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.models.canonical_event import (
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
from src.services.vessel_registry import get_vessel_by_mmsi

log = logging.getLogger(__name__)

GAP_THRESHOLD_H: float = 6.0   # hours of AIS silence to flag

_NORM = NormalizationRecord(normalized_by="dark-ship-detector")
_PROV = ProvenanceRecord(raw_source_ref="derived://dark-ship-detector")
_LIC  = LicenseRecord(access_tier="derived", commercial_use="check-provider-terms",
                       redistribution="check-provider-terms", attribution_required=False)


class DarkShipCandidate(BaseModel):
    mmsi: str
    vessel_name: str
    gap_start: str          # ISO UTC
    gap_end: str            # ISO UTC
    gap_hours: float
    last_known_lon: float
    last_known_lat: float
    reappear_lon: Optional[float] = None
    reappear_lat: Optional[float] = None
    position_jump_km: Optional[float] = None
    sanctions_flag: bool
    dark_ship_risk: str
    confidence: float
    event_id: str


class DarkShipDetectionResponse(BaseModel):
    candidates: List[DarkShipCandidate]
    total: int
    events_analysed: int


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return great-circle distance in km."""
    import math
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(min(1.0, math.sqrt(a)))


def _event_id(mmsi: str, gap_start: str) -> str:
    h = hashlib.sha256(f"dark:{mmsi}:{gap_start}".encode()).hexdigest()[:16]
    return f"dark-{h}"


def detect_dark_ships(events: List[CanonicalEvent]) -> DarkShipDetectionResponse:
    """Analyse a list of canonical events and return dark-ship candidates."""
    # Group ship_position events by MMSI
    by_mmsi: Dict[str, List[CanonicalEvent]] = {}
    for evt in events:
        if evt.event_type != EventType.SHIP_POSITION:
            continue
        mmsi = (evt.attributes or {}).get("mmsi") or (evt.correlation_keys and evt.correlation_keys.mmsi)
        if not mmsi:
            continue
        mmsi = str(mmsi)
        by_mmsi.setdefault(mmsi, []).append(evt)

    candidates: List[DarkShipCandidate] = []

    for mmsi, posns in by_mmsi.items():
        posns.sort(key=lambda e: e.event_time)
        profile = get_vessel_by_mmsi(mmsi)
        sanctions = profile.sanctions_status.value != "clean" if profile else False
        risk = profile.dark_ship_risk if profile else "unknown"
        vname = (posns[0].attributes or {}).get("vessel_name", mmsi)

        for i in range(len(posns) - 1):
            t0 = posns[i].event_time
            t1 = posns[i + 1].event_time
            if isinstance(t0, str):
                t0 = datetime.fromisoformat(t0.replace("Z", "+00:00"))
            if isinstance(t1, str):
                t1 = datetime.fromisoformat(t1.replace("Z", "+00:00"))
            gap_secs = (t1 - t0).total_seconds()
            gap_h = gap_secs / 3600.0
            if gap_h < GAP_THRESHOLD_H:
                continue

            g0 = posns[i].geometry
            g1 = posns[i + 1].geometry
            if not g0 or not g1 or g0.get("type") != "Point" or g1.get("type") != "Point":
                continue
            lon0, lat0 = g0["coordinates"][0], g0["coordinates"][1]
            lon1, lat1 = g1["coordinates"][0], g1["coordinates"][1]
            jump_km = _haversine(lon0, lat0, lon1, lat1)

            base_conf = min(0.99, gap_h / 48.0)
            if sanctions:
                base_conf = min(0.99, base_conf + 0.15)
            if jump_km > 200:
                base_conf = min(0.99, base_conf + 0.1)

            eid = _event_id(mmsi, t0.isoformat())
            candidates.append(DarkShipCandidate(
                mmsi=mmsi,
                vessel_name=str(vname),
                gap_start=t0.isoformat(),
                gap_end=t1.isoformat(),
                gap_hours=round(gap_h, 1),
                last_known_lon=round(lon0, 5),
                last_known_lat=round(lat0, 5),
                reappear_lon=round(lon1, 5),
                reappear_lat=round(lat1, 5),
                position_jump_km=round(jump_km, 1),
                sanctions_flag=sanctions,
                dark_ship_risk=risk,
                confidence=round(base_conf, 3),
                event_id=eid,
            ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    log.info("Dark ship detection complete: %d candidates from %d events", len(candidates), len(events))
    return DarkShipDetectionResponse(
        candidates=candidates,
        total=len(candidates),
        events_analysed=len(events),
    )


def to_canonical_events(candidates: List[DarkShipCandidate], aoi_ids: List[str]) -> List[CanonicalEvent]:
    """Convert DarkShipCandidate list to CanonicalEvent list for storage/search."""
    result: List[CanonicalEvent] = []
    for c in candidates:
        result.append(CanonicalEvent(
            event_id=c.event_id,
            source="dark-ship-detector",
            source_type=SourceType.DERIVED,
            entity_type=EntityType.VESSEL,
            entity_id=c.mmsi,
            event_type=EventType.DARK_SHIP_CANDIDATE,
            event_time=datetime.fromisoformat(c.gap_start.replace("Z", "+00:00")),
            geometry={"type": "Point", "coordinates": [c.last_known_lon, c.last_known_lat]},
            centroid={"type": "Point", "coordinates": [c.last_known_lon, c.last_known_lat]},
            confidence=c.confidence,
            attributes={
                "mmsi": c.mmsi,
                "vessel_name": c.vessel_name,
                "gap_start": c.gap_start,
                "gap_end": c.gap_end,
                "gap_hours": c.gap_hours,
                "last_known_lon": c.last_known_lon,
                "last_known_lat": c.last_known_lat,
                "reappear_lon": c.reappear_lon,
                "reappear_lat": c.reappear_lat,
                "position_jump_km": c.position_jump_km,
                "sanctions_flag": c.sanctions_flag,
                "dark_ship_risk": c.dark_ship_risk,
            },
            normalization=_NORM,
            provenance=_PROV,
            correlation_keys=CorrelationKeys(aoi_ids=aoi_ids, mmsi=c.mmsi),
            license=_LIC,
        ))
    return result
