"""Satellite orbit and pass API router — Track A, Phase 2.

Endpoints
---------
GET  /api/v1/orbits                       — list all loaded satellite orbits
GET  /api/v1/orbits/{satellite_id}        — single orbit detail
GET  /api/v1/orbits/{satellite_id}/passes — predicted passes for a location
POST /api/v1/orbits/ingest                — ingest TLE text

An in-memory ``OrbitStore`` (module-level dict) is seeded on import with
ISS, Sentinel-2A, and Landsat-9 using representative TLE data.

The ``OrbitConnector`` is instantiated once at module load and owns the
``compute_passes`` / ``ingest_orbits`` logic.  The router delegates to it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.connectors.orbit_connector import OrbitConnector, orbit_to_canonical_event
from src.models.operational_layers import SatelliteOrbit, SatellitePass
from src.services.event_store import get_default_event_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orbits", tags=["orbits"])

# ────────────────────────────────────────────────────────────────────────────
# Module-level orbit store and connector instance
# ────────────────────────────────────────────────────────────────────────────

_connector = OrbitConnector()
_connector.connect()

# Seed TLE data for 3 well-known satellites (representative values; not
# operational — do NOT use for real mission planning).
_SEED_TLE = """\
ISS (ZARYA)
1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994
2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123
SENTINEL-2A
1 40697U 15028A   26094.50000000  .00000050  00000-0  17800-4 0  9991
2 40697  98.5683  62.2784 0001123  84.5271 275.6031 14.30820001562811
LANDSAT-9
1 49260U 21088A   26094.50000000  .00000032  00000-0  97100-5 0  9993
2 49260  98.2219 112.4721 0001456 100.1234 260.0000 14.57126001234567
"""

_connector.ingest_orbits(_SEED_TLE)

# The canonical orbit store (satellite_id → SatelliteOrbit)
_orbit_store: Dict[str, SatelliteOrbit] = dict(_connector._orbits)

# ────────────────────────────────────────────────────────────────────────────
# Request / response models
# ────────────────────────────────────────────────────────────────────────────

class IngestTleRequest(BaseModel):
    tle_data: str = Field(..., description="Raw TLE text — one or more triplets (name + line1 + line2)")


class IngestTleResponse(BaseModel):
    ingested: int = Field(..., description="Number of satellite orbits successfully ingested")
    satellite_ids: List[str] = Field(..., description="Satellite IDs that were ingested")


class OrbitListResponse(BaseModel):
    total: int
    orbits: List[SatelliteOrbit]


class PassListResponse(BaseModel):
    satellite_id: str
    observer_lon: float
    observer_lat: float
    horizon_hours: int
    total: int
    passes: List[SatellitePass]


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
    orbits = list(_orbit_store.values())
    return OrbitListResponse(total=len(orbits), orbits=orbits)


@router.post(
    "/ingest",
    response_model=IngestTleResponse,
    summary="Ingest TLE text and add satellite orbits to the store",
)
def ingest_tle(body: IngestTleRequest) -> IngestTleResponse:
    """Parse a block of TLE text and add the resulting orbits to the in-memory store.

    Existing entries are overwritten (upsert by ``satellite_id``).
    Ingested orbits are also written to the canonical EventStore.
    """
    new_orbits = _connector.ingest_orbits(body.tle_data)
    store = get_default_event_store()
    canonical = [orbit_to_canonical_event(o) for o in new_orbits]
    store.ingest_batch(canonical)

    for o in new_orbits:
        _orbit_store[o.satellite_id] = o

    logger.info("Orbit ingest: %d orbits loaded", len(new_orbits))
    return IngestTleResponse(
        ingested=len(new_orbits),
        satellite_ids=[o.satellite_id for o in new_orbits],
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
    """Return synthetic predicted passes for the given satellite above the observer.

    The stub uses orbital-period-based scheduling; for production, replace with
    an SGP4/SDP4 propagator backed by real TLE ephemeris.
    """
    if satellite_id not in _orbit_store:
        raise HTTPException(status_code=404, detail=f"Satellite not found: {satellite_id!r}")

    # Ensure connector has the latest orbit in case of recent ingest
    _connector._orbits[satellite_id] = _orbit_store[satellite_id]
    passes = _connector.compute_passes(satellite_id, lon, lat, horizon_hours)

    return PassListResponse(
        satellite_id=satellite_id,
        observer_lon=lon,
        observer_lat=lat,
        horizon_hours=horizon_hours,
        total=len(passes),
        passes=passes,
    )


@router.get(
    "/{satellite_id}",
    response_model=SatelliteOrbit,
    summary="Retrieve a single satellite orbit record by satellite ID",
)
def get_orbit(satellite_id: str) -> SatelliteOrbit:
    """Return the orbit record for the given satellite ID, or 404 if unknown."""
    orbit = _orbit_store.get(satellite_id)
    if orbit is None:
        raise HTTPException(status_code=404, detail=f"Satellite not found: {satellite_id!r}")
    return orbit
