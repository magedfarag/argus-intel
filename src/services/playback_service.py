"""Historical Replay Service - P2-2.

Converts the in-memory EventStore into time-ordered playback frames.
Late-arrival detection: events are processed in ingestion order (ingested_at).
Any event whose event_time falls below the running per-source maximum at
ingestion time is flagged with quality_flags += ["late-arrival"].

Materialization (P2-2.2) pre-computes windowed frame bins as an in-memory
async job so that large time windows can be pre-fetched.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

from src.models.canonical_event import CanonicalEvent
from src.models.playback import (
    MaterializeRequest,
    MaterializeJobResponse,
    PlaybackFrame,
    PlaybackJobStatus,
    PlaybackQueryRequest,
    PlaybackQueryResponse,
    WindowFrame,
)
from src.services.event_store import EventStore


def _centroid_in_bbox(
    event: CanonicalEvent,
    west: float,
    south: float,
    east: float,
    north: float,
) -> bool:
    """Return True when the event's centroid Point falls within the viewport bbox."""
    coords = event.centroid.get("coordinates", [])
    if len(coords) < 2:
        return False
    lon, lat = float(coords[0]), float(coords[1])
    return west <= lon <= east and south <= lat <= north


def standard_playback_windows() -> dict:
    """Return standard 24h / 7d / 30d playback window definitions.

    These windows are pre-defined per the Phase 1 contract freeze.
    Use with materialize_async() to warm common playback windows.

    Note: Materialization is synchronous in this implementation; call once at
    startup or on a schedule via Celery beat.

    Returns dict: {window_name: (start_time, end_time)}
    """
    now = datetime.now(timezone.utc)
    return {
        "24h":  (now - timedelta(hours=24),  now),
        "7d":   (now - timedelta(days=7),    now),
        "30d":  (now - timedelta(days=30),   now),
    }


class _MaterializeJob:
    """Mutable job record for a materialization request."""

    def __init__(self, job_id: str, request: MaterializeRequest) -> None:
        self.job_id = job_id
        self.state = "pending"
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.request = request
        self.windows: Optional[List[WindowFrame]] = None
        self.total_events: Optional[int] = None
        self.error: Optional[str] = None


class PlaybackService:
    """Provides time-ordered frame queries and async materialization over EventStore."""

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store
        self._jobs: Dict[str, _MaterializeJob] = {}
        self._lock = threading.Lock()

    def query(self, req: PlaybackQueryRequest) -> PlaybackQueryResponse:
        """Return events ordered by event_time with late-arrival flags applied."""
        from fastapi import HTTPException
        if req.end_time <= req.start_time:
            raise HTTPException(status_code=422, detail="end_time must be after start_time")

        events = self._filter_events(req)
        late_ids = self._detect_late_arrivals(events)

        events.sort(key=lambda e: e.event_time)

        frames: List[PlaybackFrame] = []
        for seq, event in enumerate(events, start=1):
            is_late = event.event_id in late_ids

            if not req.include_late_arrivals and is_late:
                continue

            if is_late:
                flags = list(event.quality_flags)
                if "late-arrival" not in flags:
                    flags.append("late-arrival")
                event = event.model_copy(update={"quality_flags": flags})

            frames.append(PlaybackFrame(sequence=seq, event=event, is_late_arrival=is_late))

        late_count = sum(1 for f in frames if f.is_late_arrival)
        sources_included = sorted({f.event.source for f in frames})

        return PlaybackQueryResponse(
            frames=frames,
            total_frames=len(frames),
            time_range={"start": req.start_time, "end": req.end_time},
            sources_included=sources_included,
            late_arrival_count=late_count,
        )

    def enqueue_materialize(self, req: MaterializeRequest) -> MaterializeJobResponse:
        """Create and immediately execute a materialization job."""
        job_id = str(uuid.uuid4())
        job = _MaterializeJob(job_id=job_id, request=req)
        with self._lock:
            self._jobs[job_id] = job
        self._run_materialization(job)
        return MaterializeJobResponse(
            job_id=job_id,
            status=job.state,
            message="Materialization complete." if job.state == "completed" else "Materialization failed.",
        )

    def get_job(self, job_id: str) -> Optional[PlaybackJobStatus]:
        """Return job status or None if the job is unknown."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        return PlaybackJobStatus(
            job_id=job.job_id,
            state=job.state,
            created_at=job.created_at,
            updated_at=job.updated_at,
            request_summary={
                "aoi_id": job.request.aoi_id,
                "start_time": job.request.start_time.isoformat(),
                "end_time": job.request.end_time.isoformat(),
                "window_size_minutes": job.request.window_size_minutes,
            },
            windows=job.windows,
            total_events=job.total_events,
            total_windows=len(job.windows) if job.windows is not None else None,
            error=job.error,
        )

    def _filter_events(self, req: PlaybackQueryRequest) -> List[CanonicalEvent]:
        """Pull matching events directly from the store applying all catalogue filters.

        P3-3.5: When ``req.viewport_bbox`` is set, only events whose centroid
        falls inside the viewport bbox are returned, further capped at
        ``req.max_events``.
        """
        with self._store._lock:
            candidates = list(self._store._events.values())

        results = [e for e in candidates if req.start_time <= e.event_time <= req.end_time]

        if req.aoi_id:
            results = [e for e in results if req.aoi_id in e.correlation_keys.aoi_ids]

        if req.event_types:
            allowed = {et.value for et in req.event_types}
            results = [e for e in results if e.event_type.value in allowed]

        if req.source_types:
            allowed_st = {st.value for st in req.source_types}
            results = [e for e in results if e.source_type.value in allowed_st]

        if req.sources:
            results = [e for e in results if e.source in req.sources]

        # P3-3.5: viewport-aware spatial filter
        if req.viewport_bbox and len(req.viewport_bbox) == 4:
            west, south, east, north = req.viewport_bbox
            results = [
                e for e in results
                if _centroid_in_bbox(e, west, south, east, north)
            ]
            return results[: req.max_events]

        return results[: req.limit]

    def _detect_late_arrivals(self, events: List[CanonicalEvent]) -> Set[str]:
        """Return event_ids that arrived late relative to their source.

        Process events in ingested_at order. An event is late when its
        event_time falls below the running per-source maximum already seen.
        """
        if not events:
            return set()

        by_ingestion = sorted(events, key=lambda e: e.ingested_at)
        source_max: Dict[str, datetime] = {}
        late_ids: Set[str] = set()

        for event in by_ingestion:
            current_max = source_max.get(event.source)
            if current_max is not None and event.event_time < current_max:
                late_ids.add(event.event_id)
            else:
                source_max[event.source] = max(
                    event.event_time,
                    source_max.get(event.source, event.event_time),
                )

        return late_ids

    def _run_materialization(self, job: _MaterializeJob) -> None:
        """Compute windowed frame bins for the materialization request."""
        try:
            job.state = "running"
            job.updated_at = datetime.now(timezone.utc)

            req = job.request
            query_req = PlaybackQueryRequest(
                geometry=req.geometry,
                aoi_id=req.aoi_id,
                start_time=req.start_time,
                end_time=req.end_time,
                source_types=req.source_types,
                event_types=req.event_types,
                limit=5000,
                include_late_arrivals=True,
            )
            playback = self.query(query_req)

            window_delta = timedelta(minutes=req.window_size_minutes)
            windows: List[WindowFrame] = []
            cursor = req.start_time

            while cursor < req.end_time:
                window_end = min(cursor + window_delta, req.end_time)
                window_frames = [
                    f for f in playback.frames
                    if cursor <= f.event.event_time < window_end
                ]
                windows.append(WindowFrame(
                    window_start=cursor,
                    window_end=window_end,
                    event_count=len(window_frames),
                    event_ids=[f.event.event_id for f in window_frames],
                    late_arrival_count=sum(1 for f in window_frames if f.is_late_arrival),
                ))
                cursor = window_end

            job.windows = windows
            job.total_events = playback.total_frames
            job.state = "completed"
            job.updated_at = datetime.now(timezone.utc)

        except Exception as exc:  # noqa: BLE001
            job.state = "failed"
            job.error = str(exc)
            job.updated_at = datetime.now(timezone.utc)