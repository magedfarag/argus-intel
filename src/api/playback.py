"""Historical Replay Service router — P2-2.

POST /api/v1/playback/query        — time-ordered canonical event query
POST /api/v1/playback/materialize  — enqueue async frame pre-computation
GET  /api/v1/playback/jobs/{id}    — check materialization job status
GET  /api/v1/playback/entities/{entity_id} — entity-specific track query (P3-3.4)
"""
# ── Unified Historical Query Contract (Phase 1 Track C) ──────────────────────
#
# CANONICAL REPLAY PATH (all layer types, temporal ordering):
#   POST /api/v1/playback/query → PlaybackService.query() → EventStore
#   - Ship, aircraft, imagery, contextual, GDELT events
#   - Late-arrival detection, viewport filtering, time ordering
#
# ENTITY TRACK PATH (dense point sequences per entity):
#   GET /api/v1/playback/entities/{id} → TelemetryStore.query_entity()
#   - AIS/ADS-B position sequences for TripsLayer rendering
#   - Entity-keyed bucketing; uniform subsampling at max_points cap
#
# Both stores are populated by the same polling tasks (Wave 1 / Track B).
# Both are served from this router — one unified API surface.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.cache.query_cache import get_query_cache, ttl_for_window
from app.rate_limiter import heavy_endpoint_rate_limit
from src.api.aois import get_aoi_store
from src.models.playback import (
    EntityTrackPoint,
    EntityTrackResponse,
    MaterializeJobResponse,
    MaterializeRequest,
    PlaybackJobStatus,
    PlaybackQueryRequest,
    PlaybackQueryResponse,
)
from src.services.event_store import EventStore, get_default_event_store
from src.services.playback_service import PlaybackService
from src.services.telemetry_store import TelemetryStore, get_default_telemetry_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])

# ── Singleton services ────────────────────────────────────────────────────────
# Bound to the process-wide singletons from Track B so that when pollers write
# via get_default_event_store() / get_default_telemetry_store() the playback
# API reads the same in-memory data.
#
# _service is lazy (None until first request) so that test injection via
# set_event_store() takes effect before the first request arrives.  Job state
# lives on the PlaybackService instance, so the reference must be stable across
# enqueue_materialize → get_job call pairs.
_service: PlaybackService | None = None


def _get_service() -> PlaybackService:
    """Return a PlaybackService bound to the process-wide EventStore singleton."""
    global _service
    if _service is None:
        _service = PlaybackService(get_default_event_store())
    return _service


def _get_telemetry() -> TelemetryStore:
    """Return the process-wide TelemetryStore singleton."""
    return get_default_telemetry_store()


# ── Backward-compatible public helpers (used by router endpoints and tests) ───

def get_playback_service() -> PlaybackService:
    """Return the PlaybackService bound to the unified EventStore singleton."""
    return _get_service()


def get_telemetry_store() -> TelemetryStore:
    """Return the TelemetryStore singleton."""
    return _get_telemetry()


def set_event_store(store: EventStore) -> None:
    """Inject a pre-populated EventStore.

    Updates the process-wide singleton so that pollers and the playback API
    share the same store after injection, then resets the cached service so
    the next request picks up the new store.
    """
    import src.services.event_store as _es_mod
    _es_mod._default_store = store
    global _service
    _service = PlaybackService(store)


def set_telemetry_store(store: TelemetryStore) -> None:
    """Inject a pre-populated TelemetryStore.  Updates the process-wide singleton."""
    import src.services.telemetry_store as _ts_mod
    _ts_mod._default_store = store


def _resolve_aoi_geometry(aoi_id: str | None) -> dict | None:
    """Resolve AOI ids to geometry for playback filtering and cache consistency."""
    if not aoi_id:
        return None
    aoi = get_aoi_store().get(aoi_id)
    if not aoi:
        return None
    geometry = aoi.geometry
    return geometry.model_dump() if hasattr(geometry, "model_dump") else geometry


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/query",
    response_model=PlaybackQueryResponse,
    summary="Query canonical events ordered by event_time for map playback",
    description=(
        "Returns all matching events in ascending event_time order. "
        "Late-arriving events (event_time behind the running per-source maximum) "
        "are automatically flagged with quality_flags += ['late-arrival']."
    ),
)
def query_playback(
    req: PlaybackQueryRequest,
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> Response:
    if req.geometry is None and req.aoi_id:
        resolved_geometry = _resolve_aoi_geometry(req.aoi_id)
        if resolved_geometry is not None:
            req = req.model_copy(update={"geometry": resolved_geometry})
    if req.end_time <= req.start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_time must be after start_time",
        )
    # Build a stable cache key from the request fields that affect results.
    # Round start/end to the nearest minute so near-duplicate requests hit the cache.
    start_m = req.start_time.replace(second=0, microsecond=0)
    end_m = req.end_time.replace(second=0, microsecond=0)
    key_obj = {
        "s": start_m.isoformat(),
        "e": end_m.isoformat(),
        "aoi": req.aoi_id,
        "geom": req.geometry,
        "et": sorted(et.value for et in (req.event_types or [])),
        "st": sorted(st.value for st in (req.source_types or [])),
        "src": sorted(req.sources or []),
        "lim": req.limit,
        "late": req.include_late_arrivals,
    }
    cache_key = "pb:q:" + hashlib.md5(  # noqa: S324  (non-crypto, cache key only)
        json.dumps(key_obj, sort_keys=True).encode()
    ).hexdigest()

    cache = get_query_cache()
    cached_json: str | None = cache.get(cache_key)
    if cached_json is not None:
        return Response(content=cached_json, media_type="application/json")

    window_days = (req.end_time - req.start_time).total_seconds() / 86_400
    ttl = ttl_for_window(window_days)

    svc = get_playback_service()
    result = svc.query(req)
    # Use Pydantic v2's Rust-backed serialiser (model_dump_json) instead of
    # FastAPI's jsonable_encoder + json.dumps so that the cache always stores
    # a compact, pre-serialised string.  Subsequent cache hits skip all
    # Python-level pydantic traversal entirely.
    json_str = result.model_dump_json()
    cache.set(cache_key, json_str, ttl=ttl)
    return Response(content=json_str, media_type="application/json")


@router.post(
    "/materialize",
    response_model=MaterializeJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pre-compute playback frames for a large time window (async job)",
    description=(
        "Bins events into fixed-width windows and returns a job_id. "
        "Poll GET /api/v1/playback/jobs/{job_id} for completion status and results."
    ),
)
def materialize_playback(
    req: MaterializeRequest,
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> MaterializeJobResponse:
    if req.geometry is None and req.aoi_id:
        resolved_geometry = _resolve_aoi_geometry(req.aoi_id)
        if resolved_geometry is not None:
            req = req.model_copy(update={"geometry": resolved_geometry})
    if req.end_time <= req.start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_time must be after start_time",
        )
    svc = get_playback_service()
    return svc.enqueue_materialize(req)


@router.get(
    "/jobs/{job_id}",
    response_model=PlaybackJobStatus,
    summary="Check status/results of an async materialization job",
)
def get_job(
    job_id: str,
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> PlaybackJobStatus:
    svc = get_playback_service()
    result = svc.get_job(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playback job '{job_id}' not found.",
        )
    return result


@router.get(
    "/entities/{entity_id}",
    response_model=EntityTrackResponse,
    summary="Return time-ordered track positions for a single entity (P3-3.4)",
    description=(
        "Returns ship or aircraft position events for the given MMSI, ICAO24, or "
        "other entity identifier within the requested time window.  Results are "
        "sorted by event_time ascending and hard-capped at max_points.  When the "
        "result count exceeds max_points, a uniform subsample is returned that "
        "preserves the first and last points."
    ),
)
def get_entity_track(
    entity_id: str,
    start_time: datetime = Query(..., description="Window start (UTC ISO-8601)"),
    end_time: datetime = Query(..., description="Window end (UTC ISO-8601)"),
    source: str | None = Query(default=None, description="Filter by connector source id"),
    max_points: int = Query(default=2_000, ge=1, le=10_000, description="Maximum track points"),
) -> EntityTrackResponse:
    if end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_time must be after start_time",
        )

    # Cache look-up — TTL scaled by window width
    window_days = (end_time - start_time).total_seconds() / 86400.0
    cache_key = (
        f"playback:entity_track:{entity_id}"
        f":{start_time.isoformat()}:{end_time.isoformat()}"
        f":{source}:{max_points}"
    )
    qc = get_query_cache()
    cached = qc.get(cache_key)
    if cached is not None:
        return cached

    store = get_telemetry_store()
    events = store.query_entity(entity_id, start_time, end_time, max_points=max_points)

    # Source filter (applied post-query as the store bucketing is entity-keyed)
    if source:
        events = [e for e in events if e.source == source]

    track_points: list[EntityTrackPoint] = []
    inferred_entity_type = ""
    inferred_source: str | None = None

    for event in events:
        coords = event.centroid.get("coordinates", [])
        if len(coords) < 2:
            coords = event.geometry.get("coordinates", [])
        if len(coords) < 2:
            continue
        track_points.append(EntityTrackPoint(
            event_id=event.event_id,
            event_time=event.event_time,
            lon=float(coords[0]),
            lat=float(coords[1]),
            altitude_m=event.altitude_m,
            attributes=event.attributes,
        ))
        if not inferred_entity_type:
            inferred_entity_type = event.entity_type.value
        if not inferred_source:
            inferred_source = event.source

    if not track_points:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No track positions found for entity '{entity_id}' in the requested window.",
        )

    response = EntityTrackResponse(
        entity_id=entity_id,
        entity_type=inferred_entity_type,
        source=inferred_source,
        point_count=len(track_points),
        track_points=track_points,
        time_range={"start": start_time, "end": end_time},
    )
    qc.set(cache_key, response, ttl=ttl_for_window(window_days))
    return response
