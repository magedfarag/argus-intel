"""Export service — generate CSV and GeoJSON bundles from event search results (P1-5).

License-aware filtering is enforced from the first line: events whose
``license.redistribution`` is ``not-allowed`` are excluded from exports
unless the caller explicitly sets ``include_restricted=True`` and has the
correct role (role enforcement is a future P5-3.3 task; the flag is present
from day 1 to avoid API breakage).

Export jobs are ephemeral: files are generated on-the-fly and streamed back
to the caller.  Persistent job IDs (P1-5.2) use the in-memory job store until
PostGIS-backed persistence is ready.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from src.models.canonical_event import CanonicalEvent
from src.models.event_search import EventSearchRequest
from src.services.event_store import EventStore

log = logging.getLogger(__name__)

# ── License helpers ────────────────────────────────────────────────────────────

_BLOCKED_REDISTRIBUTION = frozenset({"not-allowed"})


def _is_exportable(event: CanonicalEvent, include_restricted: bool = False) -> bool:
    """Return True when the event's license permits redistribution."""
    if include_restricted:
        return True
    redistribution = event.license.redistribution if event.license else "check-provider-terms"
    return redistribution not in _BLOCKED_REDISTRIBUTION


# ── Export job store ──────────────────────────────────────────────────────────

_JOB_TTL_SECONDS = 3600  # Completed jobs kept for 1 hour


class ExportJob:
    """Lightweight export job record."""
    def __init__(self, job_id: str, format_: str, event_count: int) -> None:
        self.job_id = job_id
        self.format = format_
        self.event_count = event_count
        self.status: str = "pending"  # pending | completed | failed
        self.error: Optional[str] = None
        self.payload: Optional[bytes] = None  # serialised export content
        self.created_at: datetime = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None


class ExportJobStore:
    """Thread-safe in-memory store for export jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, ExportJob] = {}
        self._lock = threading.Lock()

    def put(self, job: ExportJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[ExportJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


# Module-level singleton
_job_store = ExportJobStore()


def get_job_store() -> ExportJobStore:
    return _job_store


# ── Serializers ────────────────────────────────────────────────────────────────

_CSV_COLUMNS = [
    "event_id", "event_type", "source", "source_type", "entity_type", "entity_id",
    "event_time", "confidence", "quality_flags", "centroid_lon", "centroid_lat",
]


def _centroid_coords(event: CanonicalEvent) -> tuple[Optional[float], Optional[float]]:
    """Extract (lon, lat) from a GeoJSON Point centroid dict."""
    centroid = event.centroid
    if not centroid or centroid.get("type") != "Point":
        return None, None
    coords = centroid.get("coordinates", [])
    if len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    return None, None


def events_to_csv(events: Sequence[CanonicalEvent]) -> bytes:
    """Serialise events to a UTF-8 CSV byte string."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for ev in events:
        lon, lat = _centroid_coords(ev)
        row: Dict[str, Any] = {
            "event_id": ev.event_id,
            "event_type": ev.event_type.value,
            "source": ev.source,
            "source_type": ev.source_type.value,
            "entity_type": ev.entity_type.value,
            "entity_id": ev.entity_id or "",
            "event_time": ev.event_time.isoformat(),
            "confidence": ev.confidence if ev.confidence is not None else "",
            "quality_flags": ",".join(ev.quality_flags),
            "centroid_lon": lon if lon is not None else "",
            "centroid_lat": lat if lat is not None else "",
        }
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def events_to_geojson(events: Sequence[CanonicalEvent]) -> bytes:
    """Serialise events to a GeoJSON FeatureCollection byte string."""
    features: List[Dict[str, Any]] = []
    for ev in events:
        geometry = ev.geometry or ev.centroid
        props: Dict[str, Any] = {
            "event_id": ev.event_id,
            "event_type": ev.event_type.value,
            "source": ev.source,
            "entity_type": ev.entity_type.value,
            "entity_id": ev.entity_id,
            "event_time": ev.event_time.isoformat(),
            "confidence": ev.confidence,
            "quality_flags": ev.quality_flags,
        }
        features.append({"type": "Feature", "geometry": geometry, "properties": props})
    collection = {
        "type": "FeatureCollection",
        "features": features,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(collection, default=str).encode("utf-8")


# ── ExportService ───────────────────────────────────────────────────────────────


class ExportService:
    """Orchestrates event export to CSV / GeoJSON formats."""

    def __init__(self, event_store: EventStore, job_store: ExportJobStore) -> None:
        self._events = event_store
        self._jobs = job_store

    def create_export(
        self,
        search_request: EventSearchRequest,
        format_: str,
        include_restricted: bool = False,
    ) -> ExportJob:
        """Run a synchronous export and return the completed job.

        In a future iteration this will be promoted to an async Celery task
        for very large result sets (>10 k events).
        """
        job_id = str(uuid4())
        search_result = self._events.search(search_request)
        allowed = [
            ev for ev in search_result.events
            if _is_exportable(ev, include_restricted=include_restricted)
        ]
        excluded = len(search_result.events) - len(allowed)
        if excluded:
            log.info(
                "Export license filter: excluded %d events",
                excluded,
                extra={"job_id": job_id},
            )

        job = ExportJob(job_id=job_id, format_=format_, event_count=len(allowed))
        self._jobs.put(job)

        try:
            if format_ == "csv":
                job.payload = events_to_csv(allowed)
            elif format_ == "geojson":
                job.payload = events_to_geojson(allowed)
            else:
                raise ValueError(f"Unsupported export format: {format_!r}")
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
            log.error("Export failed", exc_info=True, extra={"job_id": job_id})

        self._jobs.put(job)
        return job

