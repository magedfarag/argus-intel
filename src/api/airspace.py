"""Airspace restriction and NOTAM API router — Track B, Phase 2.

Endpoints
---------
GET  /api/v1/airspace/restrictions                     — list restrictions
GET  /api/v1/airspace/restrictions/{restriction_id}    — single restriction
GET  /api/v1/airspace/notams                           — list NOTAMs
GET  /api/v1/airspace/notams/{notam_id}                — single NOTAM

Data is served from the ``AirspaceLayerService`` singleton, which is seeded
at app startup and supports a live-connector swap (ARCH-01 / ARCH-02 pattern).
Routes no longer maintain module-level seeded stores.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.connectors.airspace_connector import AirspaceConnector
from src.models.operational_layers import AirspaceRestriction, NotamEvent
from src.services.operational_layer_service import get_airspace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/airspace", tags=["airspace"])

# ────────────────────────────────────────────────────────────────────────────
# Response models
# ────────────────────────────────────────────────────────────────────────────

class RestrictionListResponse(BaseModel):
    total: int
    active_only: bool
    restrictions: list[AirspaceRestriction]
    is_demo_data: bool = Field(default=False, description="True when backed by stub/demo data")


class NotamListResponse(BaseModel):
    total: int
    icao_filter: str | None
    notams: list[NotamEvent]
    is_demo_data: bool = Field(default=False, description="True when backed by stub/demo data")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _parse_bbox(bbox_str: str | None) -> tuple | None:
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
    bbox: str | None = Query(
        default=None,
        description="Bounding box filter: lon1,lat1,lon2,lat2 (WGS-84 decimal degrees)",
    ),
) -> RestrictionListResponse:
    """Return airspace restrictions from the service store.

    - ``active_only=true`` (default): compares UTC now against ``valid_from`` /
      ``valid_to``; restrictions outside the active window are excluded.
    - ``bbox``: comma-separated ``lon1,lat1,lon2,lat2``; centroid-based filter.
    """
    parsed_bbox = None
    if bbox:
        try:
            parsed_bbox = _parse_bbox(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    svc = get_airspace_service()
    candidates = list(svc.all_restrictions().values())

    if active_only:
        candidates = [r for r in candidates if AirspaceConnector.is_active(r)]

    if parsed_bbox is not None:
        min_lon, min_lat, max_lon, max_lat = parsed_bbox
        filtered: list[AirspaceRestriction] = []
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
        is_demo_data=svc.is_demo_mode,
    )


@router.get(
    "/restrictions/{restriction_id}",
    response_model=AirspaceRestriction,
    summary="Retrieve a single airspace restriction by ID",
)
def get_restriction(restriction_id: str) -> AirspaceRestriction:
    """Return the restriction record for the given ID, or 404 if unknown."""
    restriction = get_airspace_service().get_restriction(restriction_id)
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
    icao: str | None = Query(
        default=None,
        description="ICAO 4-letter location indicator to filter by (e.g. 'KDCA')",
        min_length=3,
        max_length=4,
    ),
) -> NotamListResponse:
    """Return NOTAMs from the service store.

    - ``icao``: case-insensitive match against ``NotamEvent.location_icao``.
    """
    svc = get_airspace_service()
    candidates = list(svc.all_notams().values())

    if icao is not None:
        upper = icao.upper()
        candidates = [n for n in candidates if n.location_icao and n.location_icao.upper() == upper]

    return NotamListResponse(
        total=len(candidates),
        icao_filter=icao.upper() if icao else None,
        notams=candidates,
        is_demo_data=svc.is_demo_mode,
    )


@router.get(
    "/notams/{notam_id}",
    response_model=NotamEvent,
    summary="Retrieve a single NOTAM by ID",
)
def get_notam(notam_id: str) -> NotamEvent:
    """Return the NOTAM record for the given ID, or 404 if unknown."""
    notam = get_airspace_service().get_notam(notam_id)
    if notam is None:
        raise HTTPException(status_code=404, detail=f"NOTAM not found: {notam_id!r}")
    return notam
