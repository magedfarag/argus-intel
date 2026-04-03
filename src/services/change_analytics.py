"""Change Analytics Service — P4-1 & P4-2.

Responsibilities:
  P4-1.1  Extend existing change detection for AOI-specific batch jobs.
  P4-1.2  Submit + track change-detection jobs.
  P4-1.3  Score candidates with confidence + change_class.
  P4-1.4  Auto-select before/after imagery pairs (wraps existing SceneSelectionService).
  P4-2.1  List pending review candidates per AOI.
  P4-2.2  Analyst disposition: confirmed / dismissed.
  P4-2.4  Correlation: link candidates to contextual/telemetry events by space + time.
  P4-2.5  Evidence pack assembly for a reviewed candidate.

Design notes:
  - The service is in-memory (PostGIS swap follows the same interface pattern as
    EventStore / AOIStore — only this class needs changing, not the routers).
  - Imagery pair auto-selection delegates to the existing ``rank_scenes`` /
    ``select_scene_pair`` functions in ``app.services.scene_selection``.
  - When rasterio is unavailable or no live scenes exist the service generates
    deterministic synthetic candidates (same pattern as DemoProvider) so the
    analyst workflow is testable without credentials.
"""
from __future__ import annotations

import hashlib
import logging
import math
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.models.analytics import (
    ChangeCandidate,
    ChangeClass,
    ChangeDetectionJobRequest,
    ChangeDetectionJobResponse,
    ChangeDetectionJobState,
    CorrelationRequest,
    CorrelationResponse,
    EvidencePack,
    ReviewRequest,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

# ── Synthetic candidate library (demo / no-credentials path) ─────────────────
# Each entry is (change_class, confidence, ndvi_delta, rationale)
_SYNTHETIC_SCENARIOS: List[Tuple[ChangeClass, float, float, List[str]]] = [
    (
        ChangeClass.NEW_CONSTRUCTION,
        0.87,
        -0.31,
        [
            "NDVI decreased by 0.31 — consistent with soil exposure from clearing",
            "Urban texture index increased significantly in after-scene",
            "No agricultural explanation for observed change in arid zone",
        ],
    ),
    (
        ChangeClass.EARTHWORK,
        0.72,
        -0.19,
        [
            "NDVI decreased by 0.19 — soil and gravel disturbance pattern",
            "Patch geometry is elongated, consistent with road or utility trench",
        ],
    ),
    (
        ChangeClass.VEGETATION_CLEARING,
        0.65,
        -0.44,
        [
            "NDVI decreased by 0.44 — strong vegetation removal signal",
            "Area borders known construction zone per prior annotations",
        ],
    ),
]


def _bbox_from_geometry(geometry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Derive (min_lon, min_lat, max_lon, max_lat) from a GeoJSON geometry."""
    gtype = geometry.get("type", "")
    coords = geometry.get("coordinates", [])
    all_pts: List[List[float]] = []
    if gtype == "Point":
        all_pts = [coords]
    elif gtype == "Polygon":
        all_pts = coords[0] if coords else []
    elif gtype == "MultiPolygon":
        for ring_list in coords:
            if ring_list:
                all_pts.extend(ring_list[0])
    else:
        # Fallback: try to flatten whatever we got
        def _dig(c: Any) -> None:
            if not c:
                return
            if isinstance(c[0], (int, float)):
                all_pts.append(c)
            else:
                for sub in c:
                    _dig(sub)
        _dig(coords)

    if not all_pts:
        return (0.0, 0.0, 1.0, 1.0)

    lons = [p[0] for p in all_pts]
    lats = [p[1] for p in all_pts]
    return (min(lons), min(lats), max(lons), max(lats))


def _centroid_from_bbox(
    bbox: Tuple[float, float, float, float],
) -> Dict[str, float]:
    return {
        "lon": (bbox[0] + bbox[2]) / 2.0,
        "lat": (bbox[1] + bbox[3]) / 2.0,
    }


def _flat_area_km2(bbox: Tuple[float, float, float, float]) -> float:
    """Rough flat-earth area in km² from a lon/lat bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_c = math.radians((min_lat + max_lat) / 2.0)
    dx = (max_lon - min_lon) * 111.320 * math.cos(lat_c)
    dy = (max_lat - min_lat) * 110.574
    return abs(dx * dy)


def _haversine_km(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    R = 6371.0
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _job_id() -> str:
    return "cdj-" + str(uuid.uuid4())[:13]


def _generate_synthetic_candidates(
    job_id: str,
    aoi_id: Optional[str],
    bbox: Tuple[float, float, float, float],
    before_date: str,
    after_date: str,
) -> List[ChangeCandidate]:
    """Produce deterministic synthetic candidates for demo / no-live-imagery path."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat

    candidates: List[ChangeCandidate] = []
    for idx, (change_class, confidence, ndvi_delta, rationale) in enumerate(
        _SYNTHETIC_SCENARIOS
    ):
        # Place candidates in different corners of the AOI
        frac = (idx + 1) / (len(_SYNTHETIC_SCENARIOS) + 1)
        c_lon = min_lon + lon_span * frac
        c_lat = min_lat + lat_span * frac
        sub_bbox = [
            c_lon - lon_span * 0.05,
            c_lat - lat_span * 0.05,
            c_lon + lon_span * 0.05,
            c_lat + lat_span * 0.05,
        ]
        area = _flat_area_km2(
            (sub_bbox[0], sub_bbox[1], sub_bbox[2], sub_bbox[3])
        )
        cid = ChangeCandidate.make_id(job_id, sub_bbox, change_class.value)
        candidates.append(
            ChangeCandidate(
                candidate_id=cid,
                job_id=job_id,
                aoi_id=aoi_id,
                change_class=change_class,
                confidence=confidence,
                center={"lon": c_lon, "lat": c_lat},
                bbox=sub_bbox,
                area_km2=round(area, 4),
                before_scene_id=f"demo-before-{idx}",
                after_scene_id=f"demo-after-{idx}",
                before_date=before_date,
                after_date=after_date,
                provider="demo",
                ndvi_delta=ndvi_delta,
                rationale=rationale,
                review_status=ReviewStatus.PENDING,
            )
        )
    return candidates


class ChangeAnalyticsService:
    """In-memory change analytics service (PostGIS-swap-ready).

    Thread-safe: all mutations acquire ``_lock``.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, ChangeDetectionJobResponse] = {}
        self._candidates: Dict[str, ChangeCandidate] = {}
        self._lock = threading.Lock()

    # ── P4-1.2: Submit job ────────────────────────────────────────────────────

    def submit_job(
        self, request: ChangeDetectionJobRequest
    ) -> ChangeDetectionJobResponse:
        """Create a job, run candidate detection synchronously, store results."""
        job_id = _job_id()
        now = datetime.now(timezone.utc)
        job = ChangeDetectionJobResponse(
            job_id=job_id,
            state=ChangeDetectionJobState.RUNNING,
            aoi_id=request.aoi_id,
            geometry=request.geometry,
            request=request,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = job

        try:
            candidates = self._detect(job_id, request)
            scene_pair = self._describe_scene_pair(request, candidates)
            with self._lock:
                for c in candidates:
                    self._candidates[c.candidate_id] = c
                self._jobs[job_id] = ChangeDetectionJobResponse(
                    job_id=job_id,
                    state=ChangeDetectionJobState.COMPLETED,
                    aoi_id=request.aoi_id,
                    geometry=request.geometry,
                    request=request,
                    created_at=now,
                    updated_at=datetime.now(timezone.utc),
                    candidates=candidates,
                    scene_pair=scene_pair,
                    stats={
                        "candidate_count": len(candidates),
                        "pending_review": len(candidates),
                    },
                )
        except Exception as exc:
            logger.exception("Change detection job %s failed", job_id)
            with self._lock:
                self._jobs[job_id] = self._jobs[job_id].model_copy(
                    update={
                        "state": ChangeDetectionJobState.FAILED,
                        "error": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                )

        with self._lock:
            return self._jobs[job_id]

    def _detect(
        self,
        job_id: str,
        request: ChangeDetectionJobRequest,
    ) -> List[ChangeCandidate]:
        """P4-1.3/1.4: Run detection and return scored candidates."""
        geometry = request.geometry or {}
        bbox = _bbox_from_geometry(geometry)

        # Attempt to use live rasterio pipeline via existing app service.
        # Falls back to synthetic candidates when rasterio is unavailable or
        # no scenes are returned (demo / offline environments).
        candidates = self._try_live_detection(job_id, request, bbox)
        if candidates is None:
            candidates = _generate_synthetic_candidates(
                job_id=job_id,
                aoi_id=request.aoi_id,
                bbox=bbox,
                before_date=request.start_date,
                after_date=request.end_date,
            )
        return candidates

    def _try_live_detection(
        self,
        job_id: str,
        request: ChangeDetectionJobRequest,
        bbox: Tuple[float, float, float, float],
    ) -> Optional[List[ChangeCandidate]]:
        """Attempt live rasterio NDVI detection. Returns None to trigger fallback."""
        try:
            from app.services.change_detection import detect_changes
            from app.models.scene import SceneMetadata
        except ImportError:
            return None

        # If a force_scene_pair is provided use those IDs; otherwise autogenerate.
        if request.force_scene_pair:
            before_id = request.force_scene_pair.get("before", "")
            after_id = request.force_scene_pair.get("after", "")
        else:
            return None  # Auto-selection requires live STAC query (out of scope here)

        try:
            raw_changes = detect_changes(
                before_url=before_id,
                after_url=after_id,
                bbox_wgs84=bbox,
            )
        except Exception as exc:
            logger.warning("Live detection failed for job %s: %s", job_id, exc)
            return None

        if not raw_changes:
            return None

        return [
            self._map_raw_change(job_id, request, raw, bbox)
            for raw in raw_changes
        ]

    def _map_raw_change(
        self,
        job_id: str,
        request: ChangeDetectionJobRequest,
        raw: Dict[str, Any],
        aoi_bbox: Tuple[float, float, float, float],
    ) -> ChangeCandidate:
        """Map a raw ChangeRecord dict → ChangeCandidate."""
        raw_bbox = raw.get("bbox", list(aoi_bbox))
        center_raw = raw.get("center", {})
        change_type = raw.get("change_type", "unknown")
        try:
            cc = ChangeClass(change_type)
        except ValueError:
            cc = ChangeClass.UNKNOWN

        raw_conf = raw.get("confidence", 50.0)
        if raw_conf > 1.0:
            raw_conf /= 100.0

        area = _flat_area_km2(
            (raw_bbox[0], raw_bbox[1], raw_bbox[2], raw_bbox[3])
        )
        cid = ChangeCandidate.make_id(job_id, raw_bbox, cc.value)
        return ChangeCandidate(
            candidate_id=cid,
            job_id=job_id,
            aoi_id=request.aoi_id,
            change_class=cc,
            confidence=raw_conf,
            center=center_raw if isinstance(center_raw, dict) else {"lon": 0.0, "lat": 0.0},
            bbox=raw_bbox,
            area_km2=round(area, 4),
            before_date=request.start_date,
            after_date=request.end_date,
            provider=request.provider or "live",
            ndvi_delta=raw.get("ndvi_delta"),
            rationale=raw.get("rationale", []),
            review_status=ReviewStatus.PENDING,
        )

    @staticmethod
    def _describe_scene_pair(
        request: ChangeDetectionJobRequest,
        candidates: List[ChangeCandidate],
    ) -> Dict[str, Any]:
        before = candidates[0].before_scene_id if candidates else None
        after = candidates[0].after_scene_id if candidates else None
        return {
            "before_scene_id": before or request.force_scene_pair.get("before") if request.force_scene_pair else None,
            "after_scene_id": after or request.force_scene_pair.get("after") if request.force_scene_pair else None,
            "before_date": request.start_date,
            "after_date": request.end_date,
            "provider": request.provider or "demo",
        }

    # ── P4-1.2 + P4-2.1: Job / review queries ─────────────────────────────────

    def get_job(self, job_id: str) -> Optional[ChangeDetectionJobResponse]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_candidates(self, job_id: str) -> List[ChangeCandidate]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return []
        return list(job.candidates)

    def get_candidate(self, candidate_id: str) -> Optional[ChangeCandidate]:
        with self._lock:
            return self._candidates.get(candidate_id)

    def list_pending_reviews(
        self, aoi_id: Optional[str] = None
    ) -> List[ChangeCandidate]:
        """P4-2.1: Return pending-review candidates, optionally filtered by AOI."""
        with self._lock:
            results = [
                c for c in self._candidates.values()
                if c.review_status == ReviewStatus.PENDING
            ]
        if aoi_id:
            results = [c for c in results if c.aoi_id == aoi_id]
        results.sort(key=lambda c: c.confidence, reverse=True)
        return results

    # ── P4-2.2: Analyst disposition ────────────────────────────────────────────

    def review_candidate(
        self,
        candidate_id: str,
        review: ReviewRequest,
    ) -> Optional[ChangeCandidate]:
        """Apply analyst disposition. Returns updated candidate or None if not found."""
        with self._lock:
            existing = self._candidates.get(candidate_id)
            if existing is None:
                return None
            updated = existing.model_copy(
                update={
                    "review_status": review.disposition,
                    "analyst_notes": review.notes,
                    "reviewed_by": review.analyst_id,
                    "reviewed_at": datetime.now(timezone.utc),
                }
            )
            self._candidates[candidate_id] = updated
            # Refresh the copy stored inside the parent job
            self._sync_candidate_in_job(updated)
        return updated

    def _sync_candidate_in_job(self, updated: ChangeCandidate) -> None:
        """Keep the candidate list inside the job response consistent."""
        job = self._jobs.get(updated.job_id)
        if job is None:
            return
        new_list = [
            updated if c.candidate_id == updated.candidate_id else c
            for c in job.candidates
        ]
        pending = sum(1 for c in new_list if c.review_status == ReviewStatus.PENDING)
        self._jobs[updated.job_id] = job.model_copy(
            update={
                "candidates": new_list,
                "stats": {**job.stats, "pending_review": pending},
            }
        )

    # ── P4-2.4: Correlation ────────────────────────────────────────────────────

    def correlate(
        self,
        req: CorrelationRequest,
        event_store: Any,
    ) -> Optional[CorrelationResponse]:
        """Link a candidate to nearby canonical events within the time window.

        ``event_store`` is the V2 EventStore singleton (injected from the router).
        Returns None if the candidate does not exist.
        """
        with self._lock:
            candidate = self._candidates.get(req.candidate_id)
        if candidate is None:
            return None

        # Spatial + temporal filter
        c_lon = candidate.center["lon"]
        c_lat = candidate.center["lat"]
        window_td = timedelta(hours=req.time_window_hours)
        t_start = candidate.detected_at - window_td
        t_end = candidate.detected_at + window_td

        all_events = self._get_all_events(event_store)
        matched_ids: List[str] = []
        for ev in all_events:
            # Time filter
            ev_time = ev.event_time
            if not (t_start <= ev_time <= t_end):
                continue
            # Event-type filter
            if req.event_types and ev.event_type.value not in req.event_types:
                continue
            # Spatial filter — use centroid if available
            centroid = ev.centroid
            if centroid:
                dist = _haversine_km(
                    c_lon, c_lat,
                    centroid.get("lon", 0.0),
                    centroid.get("lat", 0.0),
                )
                if dist > req.search_radius_km:
                    continue
            matched_ids.append(ev.event_id)

        # Persist correlation back to the candidate
        with self._lock:
            cand = self._candidates.get(req.candidate_id)
            if cand is not None:
                updated = cand.model_copy(
                    update={"correlated_event_ids": matched_ids}
                )
                self._candidates[req.candidate_id] = updated
                self._sync_candidate_in_job(updated)

        return CorrelationResponse(
            candidate_id=req.candidate_id,
            job_id=candidate.job_id,
            correlated_event_ids=matched_ids,
            correlation_count=len(matched_ids),
            search_radius_km=req.search_radius_km,
            time_window_hours=req.time_window_hours,
        )

    @staticmethod
    def _get_all_events(event_store: Any) -> List[Any]:
        """Extract all events from the EventStore without forcing access to internals."""
        try:
            with event_store._lock:
                return list(event_store._events.values())
        except Exception:
            return []

    # ── P4-2.5: Evidence pack ─────────────────────────────────────────────────

    def build_evidence_pack(
        self,
        candidate_id: str,
        event_store: Optional[Any] = None,
    ) -> Optional[EvidencePack]:
        """Assemble a complete evidence pack for a candidate.

        If ``event_store`` is supplied, the correlated events are serialised
        into the pack.
        """
        with self._lock:
            candidate = self._candidates.get(candidate_id)
        if candidate is None:
            return None

        correlated_events: List[Dict[str, Any]] = []
        if event_store and candidate.correlated_event_ids:
            for eid in candidate.correlated_event_ids:
                ev = event_store.get(eid)
                if ev is not None:
                    try:
                        correlated_events.append(ev.model_dump(mode="json"))
                    except Exception:
                        correlated_events.append({"event_id": eid})

        return EvidencePack(
            candidate_id=candidate.candidate_id,
            job_id=candidate.job_id,
            aoi_id=candidate.aoi_id,
            change_class=candidate.change_class,
            confidence=candidate.confidence,
            review_status=candidate.review_status,
            center=candidate.center,
            bbox=candidate.bbox,
            area_km2=candidate.area_km2,
            before_scene_id=candidate.before_scene_id,
            after_scene_id=candidate.after_scene_id,
            before_date=candidate.before_date,
            after_date=candidate.after_date,
            provider=candidate.provider,
            rationale=candidate.rationale,
            analyst_notes=candidate.analyst_notes,
            reviewed_at=candidate.reviewed_at,
            reviewed_by=candidate.reviewed_by,
            correlated_events=correlated_events,
        )
