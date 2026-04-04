"""In-memory canonical event store — backing layer for the V2 event search API.

This is the in-memory implementation (P1-4). It is replaced by a PostGIS-backed
store in P0-4 once the database migration runs. The interface is kept thin so
swapping backends requires only a new class without touching routers.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from src.models.canonical_event import CanonicalEvent, EventType, SourceType
from src.models.event_search import (
    EventSearchRequest,
    EventSearchResponse,
    SourceSummary,
    TimelineBucket,
    TimelineResponse,
)


class EventStore:
    """Thread-safe in-memory store for CanonicalEvents."""

    def __init__(self) -> None:
        self._events: Dict[str, CanonicalEvent] = {}
        self._lock = threading.Lock()

    def ingest(self, event: CanonicalEvent) -> None:
        """Upsert a canonical event (event_id is the primary key)."""
        with self._lock:
            self._events[event.event_id] = event

    def ingest_batch(self, events: List[CanonicalEvent]) -> None:
        with self._lock:
            for e in events:
                self._events[e.event_id] = e

    def get(self, event_id: str) -> Optional[CanonicalEvent]:
        with self._lock:
            return self._events.get(event_id)

    def search(self, req: EventSearchRequest) -> EventSearchResponse:
        """Apply AOI/time/type filters and return a paginated result."""
        with self._lock:
            candidates = list(self._events.values())

        # Time filter (mandatory)
        results = [
            e for e in candidates
            if req.start_time <= e.event_time <= req.end_time
        ]

        # AOI correlation filter
        if req.aoi_id:
            results = [e for e in results if req.aoi_id in e.correlation_keys.aoi_ids]

        # Event-type filter
        if req.event_types:
            allowed = {et.value for et in req.event_types}
            results = [e for e in results if e.event_type.value in allowed]

        # Source-type filter
        if req.source_types:
            allowed_st = {st.value for st in req.source_types}
            results = [e for e in results if e.source_type.value in allowed_st]

        # Source filter
        if req.sources:
            results = [e for e in results if e.source in req.sources]

        # Confidence filter
        if req.min_confidence is not None:
            results = [
                e for e in results
                if e.confidence is None or e.confidence >= req.min_confidence
            ]

        # Sort newest-first
        results.sort(key=lambda e: e.event_time, reverse=True)

        total = len(results)
        start = (req.page - 1) * req.page_size
        page_items = results[start : start + req.page_size]

        return EventSearchResponse(
            events=page_items,
            total=total,
            page=req.page,
            page_size=req.page_size,
            has_next=(req.page * req.page_size) < total,
        )

    def timeline(
        self,
        start_time: datetime,
        end_time: datetime,
        aoi_id: Optional[str] = None,
        bucket_minutes: int = 60,
    ) -> TimelineResponse:
        """Aggregate event counts into uniform time buckets."""
        with self._lock:
            candidates = list(self._events.values())

        window = [
            e for e in candidates
            if start_time <= e.event_time <= end_time
            and (aoi_id is None or aoi_id in e.correlation_keys.aoi_ids)
        ]

        buckets: List[TimelineBucket] = []
        delta = timedelta(minutes=bucket_minutes)
        current = start_time
        while current < end_time:
            bucket_end = min(current + delta, end_time)
            in_bucket = [e for e in window if current <= e.event_time < bucket_end]
            by_type: Dict[str, int] = {}
            for e in in_bucket:
                by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
            buckets.append(TimelineBucket(
                bucket_start=current,
                bucket_end=bucket_end,
                count=len(in_bucket),
                by_type=by_type,
            ))
            current = bucket_end

        return TimelineResponse(
            buckets=buckets,
            total_events=len(window),
            bucket_size_minutes=bucket_minutes,
        )

    def active_sources(self) -> List[SourceSummary]:
        """Return per-source event counts + last event time."""
        summary: Dict[str, SourceSummary] = {}
        with self._lock:
            events = list(self._events.values())
        for e in events:
            if e.source not in summary:
                summary[e.source] = SourceSummary(
                    connector_id=e.source,
                    display_name=e.source,
                    source_type=e.source_type.value,
                    event_count=0,
                )
            s = summary[e.source]
            s.event_count += 1
            if s.last_event_time is None or e.event_time > s.last_event_time:
                s.last_event_time = e.event_time
        return sorted(summary.values(), key=lambda s: s.event_count, reverse=True)


# Module-level singleton — used by pollers and app alike.
# Cross-process sharing requires PostgreSQL activation (see docs/ARCHITECTURE.md).
_default_store: "EventStore | None" = None


def get_default_event_store() -> "EventStore":
    """Return the process-wide EventStore singleton.

    In single-process mode (tests, dev) this provides a shared in-memory store.
    In production the store is backed by PostgreSQL once DATABASE_URL is set;
    cross-process sharing then happens transparently through the DB layer.
    """
    global _default_store
    if _default_store is None:
        _default_store = EventStore()
    return _default_store
