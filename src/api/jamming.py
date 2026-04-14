"""GPS/GNSS Jamming router — Phase 2, Track C.

GET  /api/v1/jamming/events                — list jamming events (filters: start,
                                             end, region_bbox, confidence_min)
GET  /api/v1/jamming/events/{jamming_id}   — single event detail
GET  /api/v1/jamming/heatmap               — aggregated lon/lat/weight points
POST /api/v1/jamming/ingest                — trigger stub detection for a window

IMPORTANT — DEMO-ONLY (JAM-01 / JAM-03 decision):
  No trustworthy free/open GNSS jamming public API has been approved.
  All responses are backed by the stub connector and are SYNTHETIC data.
  ``is_demo_data: true`` is always returned in every response from this router.
  This router must NOT be used as a source of truth for real jamming activity.
  See JAM-01 in the implementation plan before attempting to make this live.

Data is served from the ``JammingLayerService`` singleton (ARCH-01 / ARCH-02 pattern).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.models.operational_layers import GpsJammingEvent
from src.services.operational_layer_service import get_jamming_service

router = APIRouter(prefix="/api/v1/jamming", tags=["jamming"])


# ── Request / response models ─────────────────────────────────────────────────


class IngestRequest(BaseModel):
    """Request body for the /ingest endpoint."""
    start: datetime
    end: datetime


class HeatmapPoint(BaseModel):
    """A single weighted point for heatmap rendering."""
    lon: float
    lat: float
    weight: float


class JammingListResponse(BaseModel):
    events: list[GpsJammingEvent]
    is_demo_data: bool = Field(
        default=True,
        description="Always true — jamming data is synthetic until a live source is approved (JAM-01).",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/events",
    response_model=JammingListResponse,
    summary="List GPS/GNSS jamming events [DEMO DATA — synthetic only]",
    description=(
        "Returns **synthetic demo jamming events**. "
        "No approved public GNSS jamming feed is currently integrated. "
        "``is_demo_data`` is always ``true``. "
        "All query parameters are optional; omitting them returns all events."
    ),
)
def list_jamming_events(
    start: datetime | None = Query(
        default=None, description="Filter events detected on or after this UTC timestamp"
    ),
    end: datetime | None = Query(
        default=None, description="Filter events detected on or before this UTC timestamp"
    ),
    region_bbox: str | None = Query(
        default=None,
        description="Bounding box filter: 'min_lon,min_lat,max_lon,max_lat'",
    ),
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> JammingListResponse:
    results = list(get_jamming_service().all_events().values())

    if start is not None:
        results = [e for e in results if e.detected_at >= start]
    if end is not None:
        results = [e for e in results if e.detected_at <= end]
    if confidence_min > 0.0:
        results = [e for e in results if e.confidence >= confidence_min]

    if region_bbox is not None:
        try:
            min_lon, min_lat, max_lon, max_lat = (
                float(x) for x in region_bbox.split(",")
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail="region_bbox must be formatted as 'min_lon,min_lat,max_lon,max_lat'",
            ) from exc
        results = [
            e for e in results
            if min_lon <= e.location_lon <= max_lon
            and min_lat <= e.location_lat <= max_lat
        ]

    results.sort(key=lambda e: e.detected_at, reverse=True)
    return JammingListResponse(events=results, is_demo_data=True)


@router.get(
    "/heatmap",
    response_model=list[HeatmapPoint],
    summary="GPS jamming heatmap — aggregated lon/lat/weight points [DEMO DATA]",
    description=(
        "Returns one weighted point per synthetic jamming event. "
        "Weight is the event confidence score. "
        "Suitable for client-side heatmap rendering. "
        "Data is always synthetic (demo mode)."
    ),
)
def get_jamming_heatmap(
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> list[HeatmapPoint]:
    return [
        HeatmapPoint(lon=e.location_lon, lat=e.location_lat, weight=e.confidence)
        for e in get_jamming_service().all_events().values()
        if e.confidence >= confidence_min
    ]


@router.post(
    "/ingest",
    response_model=JammingListResponse,
    summary="Trigger stub detection and persist results [DEMO DATA]",
    description=(
        "Runs the stub jamming connector over the supplied time window, "
        "persists new events to the in-memory store, and returns them. "
        "All generated events are synthetic."
    ),
)
def ingest_jamming(body: IngestRequest) -> JammingListResponse:
    if body.end <= body.start:
        raise HTTPException(status_code=422, detail="end must be after start")

    new_events = get_jamming_service().refresh(start=body.start, end=body.end)
    return JammingListResponse(events=new_events, is_demo_data=True)


@router.get(
    "/events/{jamming_id}",
    response_model=GpsJammingEvent,
    summary="Retrieve a single GPS jamming event by ID [DEMO DATA]",
)
def get_jamming_event(jamming_id: str) -> GpsJammingEvent:
    ev = get_jamming_service().get_event(jamming_id)
    if ev is None:
        raise HTTPException(
            status_code=404, detail=f"Jamming event {jamming_id!r} not found"
        )
    return ev

