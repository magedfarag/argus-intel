"""Event search router — P1-4.

POST /api/v1/events/search     — AOI + time + source + type filter
GET  /api/v1/events/:event_id  — single event detail
GET  /api/v1/events/timeline   — aggregated event counts by time bucket
GET  /api/v1/events/sources    — list active source families

P5-1.5: When a search returns more than ``DENSITY_THRESHOLD`` events,
server-side uniform subsampling is applied before the response is returned.
The ``was_reduced`` field in the response signals that reduction occurred.
"""
from __future__ import annotations

import random
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.aois import get_aoi_store
from src.models.canonical_event import CanonicalEvent
from src.models.event_search import (
    EventSearchRequest,
    EventSearchResponse,
    SourceSummary,
    TimelineResponse,
)
from src.services.event_store import EventStore, get_default_event_store

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# ── P5-1.5: Density reduction threshold (can be overridden via AppSettings) ───
_DENSITY_THRESHOLD: int = 500
_DENSITY_MAX_RESULTS: int = 200

# ── Dependency ────────────────────────────────────────────────────────────────
# _store is the process-wide singleton.  Tests that import _store directly may
# clear _store._events for isolation.  get_event_store() always dereferences
# the current singleton so pollers, the events router, and the playback router
# share the same in-memory store.
_store: EventStore = get_default_event_store()


def get_event_store() -> EventStore:
    return get_default_event_store()


EventStoreDep = Annotated[EventStore, Depends(get_event_store)]


def _resolve_aoi_geometry(aoi_id: str | None) -> dict | None:
    """Resolve an AOI id to its geometry so searches can use spatial filtering."""
    if not aoi_id:
        return None
    aoi = get_aoi_store().get(aoi_id)
    if not aoi:
        return None
    geometry = aoi.geometry
    return geometry.model_dump() if hasattr(geometry, "model_dump") else geometry


def _apply_density_reduction(response: EventSearchResponse) -> EventSearchResponse:
    """P5-1.5: Uniformly subsample events when count exceeds the density threshold.

    Uses a seed derived from the result count for reproducible sampling
    within a single request.  The ``was_reduced`` flag is set on the response.
    """
    if len(response.events) <= _DENSITY_THRESHOLD:
        return response
    rng = random.Random(len(response.events))
    sampled = rng.sample(response.events, _DENSITY_MAX_RESULTS)
    sampled.sort(key=lambda e: e.event_time)
    return EventSearchResponse(
        events=sampled,
        total=response.total,
        was_reduced=True,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/search",
    response_model=EventSearchResponse,
    summary="Search canonical events by AOI + time + source + type",
)
def search_events(req: EventSearchRequest, store: EventStoreDep) -> EventSearchResponse:
    """Query the canonical_events store using spatial, temporal, and categorical filters.

    At minimum, start_time and end_time are required.
    Supply geometry or aoi_id to restrict to a specific area.
    When the result count exceeds the density threshold, uniform subsampling
    is applied server-side and the ``was_reduced`` flag is set in the response.
    """
    if req.end_time <= req.start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")
    if req.geometry is None and req.aoi_id:
        resolved_geometry = _resolve_aoi_geometry(req.aoi_id)
        if resolved_geometry is not None:
            req = req.model_copy(update={"geometry": resolved_geometry})
    result = store.search(req)
    return _apply_density_reduction(result)


@router.get(
    "/sources",
    response_model=list[SourceSummary],
    summary="List active source families with event counts",
)
def list_sources(store: EventStoreDep) -> list[SourceSummary]:
    """Return per-connector event counts and last-seen timestamps for the source catalog panel."""
    return store.active_sources()


@router.get(
    "/timeline",
    response_model=TimelineResponse,
    summary="Aggregated event counts bucketed by time for the timeline bar chart",
)
def get_timeline(
    store: EventStoreDep,
    start_time: datetime = Query(..., description="Window start (UTC ISO 8601)"),
    end_time: datetime = Query(..., description="Window end (UTC ISO 8601)"),
    aoi_id: str | None = Query(default=None, description="Filter to AOI correlation key"),
    bucket_minutes: int = Query(default=60, ge=1, le=1440, description="Bucket width in minutes"),
) -> TimelineResponse:
    if end_time <= start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")
    return store.timeline(
        start_time,
        end_time,
        aoi_id=aoi_id,
        geometry=_resolve_aoi_geometry(aoi_id),
        bucket_minutes=bucket_minutes,
    )


@router.get(
    "/{event_id}",
    response_model=CanonicalEvent,
    summary="Retrieve a single canonical event by ID",
)
def get_event(event_id: str, store: EventStoreDep) -> CanonicalEvent:
    event = store.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
    return event
