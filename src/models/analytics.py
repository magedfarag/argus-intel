"""Analytics models — P4-1 Change Detection Job System + P4-2 Analyst Review Workflow.

Models:
  ChangeDetectionJobRequest  — submit a batch change-detection job for an AOI
  ChangeDetectionJobState    — job lifecycle enum
  ReviewStatus               — analyst disposition enum
  ChangeClass                — canonical change-type taxonomy
  ChangeCandidate            — a single detected change candidate
  ChangeDetectionJobResponse — job status + candidates list
  ReviewRequest              — analyst disposition payload
  CorrelationRequest         — correlate a candidate with contextual events
  CorrelationResponse        — candidate + correlated event references
  EvidencePack               — exportable evidence bundle for a candidate
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────


class ChangeDetectionJobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class ChangeClass(str, Enum):
    """Canonical taxonomy of detectable construction change types."""
    NEW_CONSTRUCTION = "new_construction"
    DEMOLITION = "demolition"
    EXCAVATION = "excavation"
    EARTHWORK = "earthwork"
    FOUNDATION = "foundation"
    STRUCTURE_FRAME = "structure_frame"
    SURFACE_CHANGE = "surface_change"
    VEGETATION_CLEARING = "vegetation_clearing"
    FLOODING = "flooding"
    UNKNOWN = "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Request / response models
# ──────────────────────────────────────────────────────────────────────────────


class ChangeDetectionJobRequest(BaseModel):
    """P4-1.2: Submit a change-detection batch job for an AOI."""

    aoi_id: Optional[str] = Field(
        default=None,
        description="Reference to a stored AOI. Used to retrieve geometry if geometry omitted.",
    )
    geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON Polygon or MultiPolygon defining the area to analyse.",
    )
    start_date: str = Field(
        description="Start of imagery search window (YYYY-MM-DD).",
    )
    end_date: str = Field(
        description="End of imagery search window (YYYY-MM-DD).",
    )
    max_cloud_cover_pct: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Maximum cloud cover % to consider for scene selection.",
    )
    min_temporal_gap_days: int = Field(
        default=7,
        ge=1,
        description="Minimum days between before/after scenes.",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Preferred imagery provider (sentinel2, landsat, …). Auto-selects if omitted.",
    )
    force_scene_pair: Optional[Dict[str, str]] = Field(
        default=None,
        description="Override auto-selection: {'before': 'scene_id', 'after': 'scene_id'}.",
    )

    @model_validator(mode="after")
    def _require_aoi_or_geometry(self) -> "ChangeDetectionJobRequest":
        if not self.aoi_id and not self.geometry:
            raise ValueError("Either aoi_id or geometry must be provided.")
        return self


class ChangeCandidate(BaseModel):
    """P4-1.3: A single scored change candidate produced by the detection pipeline."""

    candidate_id: str = Field(description="Deterministic SHA-256 based ID.")
    job_id: str
    aoi_id: Optional[str] = None
    change_class: ChangeClass = Field(default=ChangeClass.UNKNOWN)
    confidence: float = Field(ge=0.0, le=1.0)
    review_status: ReviewStatus = Field(default=ReviewStatus.PENDING)
    center: Dict[str, float] = Field(
        description="{'lon': float, 'lat': float} — centroid of the changed area.",
    )
    bbox: List[float] = Field(
        description="[min_lon, min_lat, max_lon, max_lat]",
    )
    area_km2: float = Field(ge=0.0)
    before_scene_id: Optional[str] = None
    after_scene_id: Optional[str] = None
    before_date: Optional[str] = None
    after_date: Optional[str] = None
    provider: str = "demo"
    ndvi_delta: Optional[float] = None
    rationale: List[str] = Field(default_factory=list)
    analyst_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    correlated_event_ids: List[str] = Field(
        default_factory=list,
        description="event_ids from the canonical event store linked via correlation.",
    )
    quality_flags: List[str] = Field(default_factory=list)

    @classmethod
    def make_id(cls, job_id: str, bbox: List[float], change_class: str) -> str:
        key = f"{job_id}:{bbox}:{change_class}"
        return "cand-" + hashlib.sha256(key.encode()).hexdigest()[:16]


class ChangeDetectionJobResponse(BaseModel):
    """P4-1.2: Response for job status + list of candidates."""

    job_id: str
    state: ChangeDetectionJobState
    aoi_id: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    request: Optional[ChangeDetectionJobRequest] = None
    created_at: datetime
    updated_at: datetime
    candidates: List[ChangeCandidate] = Field(default_factory=list)
    scene_pair: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    """P4-2.2: Analyst disposition payload."""

    disposition: ReviewStatus = Field(
        description="confirmed or dismissed",
    )
    analyst_id: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Free-text analyst notes (evidence, caveats, references).",
    )

    @model_validator(mode="after")
    def _disposition_not_pending(self) -> "ReviewRequest":
        if self.disposition == ReviewStatus.PENDING:
            raise ValueError("disposition must be 'confirmed' or 'dismissed', not 'pending'.")
        return self


class CorrelationRequest(BaseModel):
    """P4-2.4: Correlate a change candidate with canonical events."""

    candidate_id: str
    search_radius_km: float = Field(
        default=5.0,
        ge=0.1,
        le=200.0,
        description="Spatial search radius around candidate centroid.",
    )
    time_window_hours: float = Field(
        default=720.0,
        ge=1.0,
        description="Time window (hrs) around candidate detected_at to search events.",
    )
    event_types: Optional[List[str]] = Field(
        default=None,
        description="Restrict correlation to these EventType values. All types if omitted.",
    )


class CorrelationResponse(BaseModel):
    """P4-2.4: Candidate enriched with correlated event references."""

    candidate_id: str
    job_id: str
    correlated_event_ids: List[str]
    correlation_count: int
    search_radius_km: float
    time_window_hours: float


class EvidencePack(BaseModel):
    """P4-2.5: Exportable evidence bundle for analyst review or archiving."""

    candidate_id: str
    job_id: str
    aoi_id: Optional[str] = None
    change_class: ChangeClass
    confidence: float
    review_status: ReviewStatus
    center: Dict[str, float]
    bbox: List[float]
    area_km2: float
    before_scene_id: Optional[str] = None
    after_scene_id: Optional[str] = None
    before_date: Optional[str] = None
    after_date: Optional[str] = None
    provider: str
    rationale: List[str]
    analyst_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    correlated_events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized canonical events correlated with this candidate.",
    )
    exported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    schema_version: str = "1.0"
