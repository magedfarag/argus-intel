"""GPS/GNSS Jamming router — Phase 2, Track C.

GET  /api/v1/jamming/events                — list jamming events (filters: start,
                                             end, region_bbox, confidence_min)
GET  /api/v1/jamming/events/{jamming_id}   — single event detail
GET  /api/v1/jamming/heatmap               — aggregated lon/lat/weight points
POST /api/v1/jamming/ingest                — trigger stub detection for a window

In-memory store is seeded at module load with 5 deterministic events spanning
the 30 days prior to the project reference date (2026-04-04).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.connectors.jamming_connector import JammingConnector
from src.models.operational_layers import GpsJammingEvent

router = APIRouter(prefix="/api/v1/jamming", tags=["jamming"])

# ── In-memory store ───────────────────────────────────────────────────────────
_connector = JammingConnector()
_store: Dict[str, GpsJammingEvent] = {}

# Fixed reference "now" for deterministic seeding (project-relative timestamp)
_REF_NOW = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)


def _seed_store() -> None:
    """Seed the in-memory store with 5 deterministic jamming events.

    Draws from two consecutive 30-day windows to guarantee at least 5 events
    regardless of how many the connector returns from a single window.
    """
    w1_end = _REF_NOW
    w1_start = _REF_NOW - timedelta(days=30)
    events: List[GpsJammingEvent] = _connector.detect_jamming_events(w1_start, w1_end)

    if len(events) < 5:
        w2_end = w1_start
        w2_start = _REF_NOW - timedelta(days=60)
        events.extend(_connector.detect_jamming_events(w2_start, w2_end))

    for ev in events[:5]:
        _store[ev.jamming_id] = ev


_seed_store()


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


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/events",
    response_model=List[GpsJammingEvent],
    summary="List GPS/GNSS jamming events",
    description=(
        "Returns jamming events from the in-memory store.  "
        "All query parameters are optional; omitting them returns all events."
    ),
)
def list_jamming_events(
    start: Optional[datetime] = Query(
        default=None, description="Filter events detected on or after this UTC timestamp"
    ),
    end: Optional[datetime] = Query(
        default=None, description="Filter events detected on or before this UTC timestamp"
    ),
    region_bbox: Optional[str] = Query(
        default=None,
        description="Bounding box filter: 'min_lon,min_lat,max_lon,max_lat'",
    ),
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> List[GpsJammingEvent]:
    results = list(_store.values())

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
    return results


@router.get(
    "/heatmap",
    response_model=List[HeatmapPoint],
    summary="GPS jamming heatmap — aggregated lon/lat/weight points",
    description=(
        "Returns one weighted point per jamming event.  "
        "Weight is the event confidence score.  "
        "Suitable for client-side heatmap rendering."
    ),
)
def get_jamming_heatmap(
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> List[HeatmapPoint]:
    return [
        HeatmapPoint(lon=e.location_lon, lat=e.location_lat, weight=e.confidence)
        for e in _store.values()
        if e.confidence >= confidence_min
    ]


@router.post(
    "/ingest",
    response_model=List[GpsJammingEvent],
    summary="Trigger stub detection and persist results",
    description=(
        "Runs the jamming connector over the supplied time window, "
        "persists new events to the in-memory store, and returns them."
    ),
)
def ingest_jamming(body: IngestRequest) -> List[GpsJammingEvent]:
    if body.end <= body.start:
        raise HTTPException(status_code=422, detail="end must be after start")

    new_events = _connector.detect_jamming_events(body.start, body.end)
    for ev in new_events:
        _store[ev.jamming_id] = ev
    return new_events


@router.get(
    "/events/{jamming_id}",
    response_model=GpsJammingEvent,
    summary="Retrieve a single GPS jamming event by ID",
)
def get_jamming_event(jamming_id: str) -> GpsJammingEvent:
    ev = _store.get(jamming_id)
    if ev is None:
        raise HTTPException(
            status_code=404, detail=f"Jamming event {jamming_id!r} not found"
        )
    return ev
