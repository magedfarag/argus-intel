"""Vessel registry REST API — P6-2.

GET /api/v1/vessels          — list vessels (filter by sanctions, dark risk, type)
GET /api/v1/vessels/mmsi/{mmsi} — vessel profile by MMSI
GET /api/v1/vessels/imo/{imo}   — vessel profile by IMO
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.services.vessel_registry import (
    VesselProfile,
    get_vessel_by_imo,
    get_vessel_by_mmsi,
    list_vessels,
)

router = APIRouter(prefix="/api/v1/vessels", tags=["vessels"])


@router.get("", response_model=List[VesselProfile], summary="List vessels")
def list_all_vessels(
    sanctions_only: bool = Query(False, description="Return only sanctioned/shadow-fleet vessels"),
    dark_risk: Optional[str] = Query(None, description="Filter by dark_ship_risk: critical/high/medium/low"),
    vessel_type: Optional[str] = Query(None, description="Filter by vessel type (case-insensitive)"),
    limit: int = Query(100, ge=1, le=500),
) -> List[VesselProfile]:
    return list_vessels(sanctions_only=sanctions_only, dark_risk=dark_risk, vessel_type=vessel_type, limit=limit)


@router.get("/mmsi/{mmsi}", response_model=VesselProfile, summary="Vessel by MMSI")
def get_by_mmsi(mmsi: str) -> VesselProfile:
    v = get_vessel_by_mmsi(mmsi)
    if not v:
        raise HTTPException(status_code=404, detail=f"Vessel with MMSI '{mmsi}' not found")
    return v


@router.get("/imo/{imo}", response_model=VesselProfile, summary="Vessel by IMO")
def get_by_imo(imo: str) -> VesselProfile:
    v = get_vessel_by_imo(imo)
    if not v:
        raise HTTPException(status_code=404, detail=f"Vessel with IMO '{imo}' not found")
    return v
