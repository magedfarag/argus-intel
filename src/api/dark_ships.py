"""Dark ship detection REST API — P6-5.

POST /api/v1/dark-ships/detect   — run detection on an event stream
GET  /api/v1/dark-ships          — curated demo dark-ship candidates
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.canonical_event import CanonicalEvent
from src.services.dark_ship_detector import (
    DarkShipCandidate,
    DarkShipDetectionResponse,
    detect_dark_ships,
)

router = APIRouter(prefix="/api/v1/dark-ships", tags=["dark-ships"])


class DetectRequest(BaseModel):
    events: List[CanonicalEvent]


@router.post(
    "/detect",
    response_model=DarkShipDetectionResponse,
    summary="Detect dark-ship candidates from a list of canonical AIS events",
)
def detect(req: DetectRequest) -> DarkShipDetectionResponse:
    if not req.events:
        raise HTTPException(status_code=422, detail="events list must not be empty")
    return detect_dark_ships(req.events)


# ── Curated demo endpoint ─────────────────────────────────────────────────────
# Returns a deterministic list of dark-ship candidates seeded from demo data.
# This guarantees the UI has data without needing a live AIS feed.

_DEMO_CANDIDATES: List[DarkShipCandidate] = [
    DarkShipCandidate(
        mmsi="9169501", vessel_name="WISDOM",
        gap_start="2026-03-10T04:22:00+00:00",
        gap_end="2026-03-12T09:15:00+00:00",
        gap_hours=52.9,
        last_known_lon=56.28, last_known_lat=26.44,
        reappear_lon=57.10, reappear_lat=25.92,
        position_jump_km=103.7,
        sanctions_flag=True, dark_ship_risk="critical",
        confidence=0.97,
        event_id="dark-demo-001",
    ),
    DarkShipCandidate(
        mmsi="9154671", vessel_name="HORSE",
        gap_start="2026-03-18T22:00:00+00:00",
        gap_end="2026-03-21T06:40:00+00:00",
        gap_hours=56.7,
        last_known_lon=55.98, last_known_lat=26.55,
        reappear_lon=57.75, reappear_lat=24.80,
        position_jump_km=217.4,
        sanctions_flag=True, dark_ship_risk="critical",
        confidence=0.99,
        event_id="dark-demo-002",
    ),
    DarkShipCandidate(
        mmsi="9219208", vessel_name="SEA ROSE",
        gap_start="2026-03-25T11:10:00+00:00",
        gap_end="2026-03-26T21:55:00+00:00",
        gap_hours=34.7,
        last_known_lon=56.62, last_known_lat=26.30,
        reappear_lon=54.88, reappear_lat=27.12,
        position_jump_km=182.9,
        sanctions_flag=True, dark_ship_risk="critical",
        confidence=0.94,
        event_id="dark-demo-003",
    ),
]


@router.get(
    "",
    response_model=DarkShipDetectionResponse,
    summary="List curated demo dark-ship candidates",
)
def list_demo_candidates() -> DarkShipDetectionResponse:
    return DarkShipDetectionResponse(
        candidates=_DEMO_CANDIDATES,
        total=len(_DEMO_CANDIDATES),
        events_analysed=0,
    )
