"""Airspace restriction and NOTAM API router — Track B, Phase 2.

Endpoints
---------
GET  /api/v1/airspace/restrictions                     — list restrictions
GET  /api/v1/airspace/restrictions/{restriction_id}    — single restriction
GET  /api/v1/airspace/notams                           — list NOTAMs
GET  /api/v1/airspace/notams/{notam_id}                — single NOTAM

In-memory stores (module-level dicts) are seeded at import time from the
``AirspaceConnector`` stub data.  The ``active_only`` query parameter on the
list endpoints filters by real-time UTC comparison.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.connectors.airspace_connector import (
    AirspaceConnector,
    notam_to_canonical_event,
    restriction_to_canonical_event,
)
from src.models.operational_layers import AirspaceRestriction, NotamEvent
from src.services.event_store import get_default_event_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/airspace", tags=["airspace"])

# ────────────────────────────────────────────────────────────────────────────
# Module-level stores seeded from connector stub
# ────────────────────────────────────────────────────────────────────────────

_connector = AirspaceConnector()
_connector.connect()

# Restriction store: restriction_id → AirspaceRestriction
_restriction_store: Dict[str, AirspaceRestriction] = {
    r.restriction_id: r for r in _connector.fetch_restrictions()
}

# NOTAM store: notam_id → NotamEvent
_notam_store: Dict[str, NotamEvent] = {
    n.notam_id: n for n in _connector.fetch_notams()
}

# Push seed data into the canonical EventStore so events appear in searches.
_event_store = get_default_event_store()
_event_store.ingest_batch(
    [restriction_to_canonical_event(r) for r in _restriction_store.values()]
    + [notam_to_canonical_event(n) for n in _notam_store.values()]
)

# ────────────────────────────────────────────────────────────────────────────
# Response models
# ────────────────────────────────────────────────────────────────────────────

class RestrictionListResponse(BaseModel):
    total: int
    active_only: bool
    restrictions: List[AirspaceRestriction]


class NotamListResponse(BaseModel):
    total: int
    icao_filter: Optional[str]
    notams: List[NotamEvent]


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _parse_bbox(bbox_str: Optional[str]) -> Optional[tuple]:
    """Parse a ``lon1,lat1,lon2,lat2`` string into a 4-tuple of floats.

    Returns ``None`` if ``bbox_str`` is None or empty.
    Raises ``ValueError`` on malformed input (propagated as HTTP 422 by FastAPI).
    """
    if not bbox_str:
        return None
    parts = bbox_str.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must have exactly 4 comma-separated values: lon1,lat1,lon2,lat2")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p.strip()) for p in parts)
    except ValueError as exc:
        raise ValueError(f"bbox values must be numeric floats: {exc}") from exc
    return (min_lon, min_lat, max_lon, max_lat)


# ────────────────────────────────────────────────────────────────────────────
# Restriction endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/restrictions",
    response_model=RestrictionListResponse,
    summary="List airspace restrictions, optionally filtered by active status and bounding box",
)
def list_restrictions(
    active_only: bool = Query(default=True, description="Return only currently active restrictions"),
    bbox: Optional[str] = Query(
        default=None,
        description="Bounding box filter: lon1,lat1,lon2,lat2 (WGS-84 decimal degrees)",
    ),
) -> RestrictionListResponse:
    """Return airspace restrictions from the in-memory store.

    - ``active_only=true`` (default): compares UTC now against ``valid_from`` /
      ``valid_to``; restrictions outside the active window are excluded.
    - ``bbox``: comma-separated ``lon1,lat1,lon2,lat2``; centroid-based filter.
    """
    parsed_bbox = None
    if bbox:
        try:
            parsed_bbox = _parse_bbox(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    candidates = list(_restriction_store.values())

    if active_only:
        candidates = [r for r in candidates if AirspaceConnector.is_active(r)]

    if parsed_bbox is not None:
        min_lon, min_lat, max_lon, max_lat = parsed_bbox
        filtered: List[AirspaceRestriction] = []
        for r in candidates:
            coords = r.geometry_geojson.get("coordinates", [[]])[0]
            if not coords:
                continue
            clon = sum(c[0] for c in coords) / len(coords)
            clat = sum(c[1] for c in coords) / len(coords)
            if min_lon <= clon <= max_lon and min_lat <= clat <= max_lat:
                filtered.append(r)
        candidates = filtered

    return RestrictionListResponse(
        total=len(candidates),
        active_only=active_only,
        restrictions=candidates,
    )


@router.get(
    "/restrictions/{restriction_id}",
    response_model=AirspaceRestriction,
    summary="Retrieve a single airspace restriction by ID",
)
def get_restriction(restriction_id: str) -> AirspaceRestriction:
    """Return the restriction record for the given ID, or 404 if unknown."""
    restriction = _restriction_store.get(restriction_id)
    if restriction is None:
        raise HTTPException(status_code=404, detail=f"Restriction not found: {restriction_id!r}")
    return restriction


# ────────────────────────────────────────────────────────────────────────────
# NOTAM endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/notams",
    response_model=NotamListResponse,
    summary="List NOTAMs, optionally filtered by ICAO location code",
)
def list_notams(
    icao: Optional[str] = Query(
        default=None,
        description="ICAO 4-letter location indicator to filter by (e.g. 'KDCA')",
        min_length=3,
        max_length=4,
    ),
) -> NotamListResponse:
    """Return NOTAMs from the in-memory store.

    - ``icao``: case-insensitive match against ``NotamEvent.location_icao``.
    """
    candidates = list(_notam_store.values())

    if icao is not None:
        upper = icao.upper()
        candidates = [n for n in candidates if n.location_icao and n.location_icao.upper() == upper]

    return NotamListResponse(
        total=len(candidates),
        icao_filter=icao.upper() if icao else None,
        notams=candidates,
    )


@router.get(
    "/notams/{notam_id}",
    response_model=NotamEvent,
    summary="Retrieve a single NOTAM by ID",
)
def get_notam(notam_id: str) -> NotamEvent:
    """Return the NOTAM record for the given ID, or 404 if unknown."""
    notam = _notam_store.get(notam_id)
    if notam is None:
        raise HTTPException(status_code=404, detail=f"NOTAM not found: {notam_id!r}")
    return notam
