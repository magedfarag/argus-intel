"""Satellite orbit and pass API router — Track A, Phase 2.

Endpoints
---------
GET  /api/v1/orbits                       — list all loaded satellite orbits
GET  /api/v1/orbits/{satellite_id}        — single orbit detail
GET  /api/v1/orbits/{satellite_id}/passes — predicted passes for a location
POST /api/v1/orbits/ingest                — ingest TLE text

Data is served from the ``OrbitLayerService`` singleton, which is seeded at
app startup and supports a live-connector swap (ARCH-01 / ARCH-02 pattern).
Routes no longer maintain module-level seeded stores.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.models.operational_layers import SatelliteOrbit, SatellitePass
from src.services.operational_layer_service import get_orbit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orbits", tags=["orbits"])

# ────────────────────────────────────────────────────────────────────────────
# Request / response models
# ────────────────────────────────────────────────────────────────────────────

class IngestTleRequest(BaseModel):
    tle_data: str = Field(..., description="Raw TLE text — one or more triplets (name + line1 + line2)")


class IngestTleResponse(BaseModel):
    ingested: int = Field(..., description="Number of satellite orbits successfully ingested")
    satellite_ids: list[str] = Field(..., description="Satellite IDs that were ingested")
    is_demo_data: bool = Field(default=False, description="True when backed by stub/demo data")


class OrbitListResponse(BaseModel):
    total: int
    orbits: list[SatelliteOrbit]
    is_demo_data: bool = Field(default=False, description="True when backed by stub/demo data")


class PassListResponse(BaseModel):
    satellite_id: str
    observer_lon: float
    observer_lat: float
    horizon_hours: int
    total: int
    passes: list[SatellitePass]
    is_demo_data: bool = Field(default=False, description="True when backed by stub/demo data")


# ────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=OrbitListResponse,
    summary="List all loaded satellite orbits",
)
def list_orbits() -> OrbitListResponse:
    """Return all satellite orbits currently loaded in the in-memory store."""
    svc = get_orbit_service()
    orbits = list(svc.all_orbits().values())
    return OrbitListResponse(total=len(orbits), orbits=orbits, is_demo_data=svc.is_demo_mode)


@router.post(
    "/ingest",
    response_model=IngestTleResponse,
    summary="Ingest TLE text and add satellite orbits to the store",
)
def ingest_tle(body: IngestTleRequest) -> IngestTleResponse:
    """Parse a block of TLE text and add the resulting orbits to the store.

    Existing entries are overwritten (upsert by ``satellite_id``).
    Ingested orbits are also written to the canonical EventStore.
    """
    svc = get_orbit_service()
    new_orbits = svc.ingest_tle(body.tle_data)
    logger.info("Orbit ingest: %d orbits loaded", len(new_orbits))
    return IngestTleResponse(
        ingested=len(new_orbits),
        satellite_ids=[o.satellite_id for o in new_orbits],
        is_demo_data=svc.is_demo_mode,
    )


@router.get(
    "/{satellite_id}/passes",
    response_model=PassListResponse,
    summary="Compute predicted passes for a satellite above an observer location",
)
def get_passes(
    satellite_id: str,
    lon: float = Query(..., description="Observer longitude (decimal degrees, WGS-84)", ge=-180.0, le=180.0),
    lat: float = Query(..., description="Observer latitude (decimal degrees, WGS-84)", ge=-90.0, le=90.0),
    horizon_hours: int = Query(default=24, ge=1, le=168, description="Lookahead window in hours"),
) -> PassListResponse:
    """Return predicted passes for the given satellite above the observer.

    In demo/stub mode uses orbital-period-based scheduling. For production,
    replace with an SGP4/SDP4 propagator backed by real TLE ephemeris (ORB-02).
    """
    svc = get_orbit_service()
    passes = svc.compute_passes(satellite_id, lon, lat, horizon_hours)
    if passes is None:
        raise HTTPException(status_code=404, detail=f"Satellite not found: {satellite_id!r}")

    return PassListResponse(
        satellite_id=satellite_id,
        observer_lon=lon,
        observer_lat=lat,
        horizon_hours=horizon_hours,
        total=len(passes),
        passes=passes,
        is_demo_data=svc.is_demo_mode,
    )


@router.get(
    "/{satellite_id}",
    response_model=SatelliteOrbit,
    summary="Retrieve a single satellite orbit record by satellite ID",
)
def get_orbit(satellite_id: str) -> SatelliteOrbit:
    """Return the orbit record for the given satellite ID, or 404 if unknown."""
    orbit = get_orbit_service().get_orbit(satellite_id)
    if orbit is None:
        raise HTTPException(status_code=404, detail=f"Satellite not found: {satellite_id!r}")
    return orbit

