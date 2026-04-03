"""Pydantic models for the Historical Replay Service (P2-2).

Covers:
  POST /api/v1/playback/query        — time-ordered canonical event query
  POST /api/v1/playback/materialize  — async pre-computation of playback frames
  GET  /api/v1/playback/jobs/{id}    — check materialization job status
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from src.models.canonical_event import CanonicalEvent, EventType, SourceType


class PlaybackQueryRequest(BaseModel):
    """POST /api/v1/playback/query — stream events ordered by event_time."""

    geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON Polygon/MultiPolygon AOI filter.",
    )
    aoi_id: Optional[str] = Field(
        default=None,
        description="Restrict query to events correlated to this AOI id.",
    )
    start_time: datetime = Field(..., description="Window start (UTC)")
    end_time: datetime = Field(..., description="Window end (UTC)")
    source_types: Optional[List[SourceType]] = Field(
        default=None,
        description="Restrict to these source category codes.",
    )
    event_types: Optional[List[EventType]] = Field(
        default=None,
        description="Restrict to these event families.",
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Restrict to specific connector identifiers.",
    )
    limit: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Maximum events to return (hard cap 5 000).",
    )
    viewport_bbox: Optional[List[float]] = Field(
        default=None,
        description=(
            "[west, south, east, north] viewport bounds (EPSG:4326). "
            "When set, only events whose centroid falls inside this bbox are returned. "
            "Requires exactly 4 elements. (P3-3.5)"
        ),
    )
    max_events: int = Field(
        default=2_000,
        ge=1,
        le=10_000,
        description="Server-side cap on returned events when viewport_bbox is active (P3-3.5).",
    )
    include_late_arrivals: bool = Field(
        default=True,
        description="Include events flagged as late-arriving in results.",
    )

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _enforce_utc(cls, v: Any) -> Any:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError("Naive datetime rejected — provide UTC-aware datetime")
        return v


class PlaybackFrame(BaseModel):
    """One time-ordered event slot in the playback sequence."""

    sequence: int = Field(..., description="1-based position in event_time order")
    event: CanonicalEvent
    is_late_arrival: bool = Field(
        default=False,
        description="True when this event's event_time falls behind the running maximum for its source.",
    )


class PlaybackQueryResponse(BaseModel):
    """Response for POST /api/v1/playback/query."""

    frames: List[PlaybackFrame]
    total_frames: int
    time_range: Dict[str, datetime]
    sources_included: List[str]
    late_arrival_count: int


class MaterializeRequest(BaseModel):
    """POST /api/v1/playback/materialize — enqueue async frame pre-computation."""

    geometry: Optional[Dict[str, Any]] = Field(default=None)
    aoi_id: Optional[str] = Field(default=None)
    start_time: datetime = Field(..., description="Window start (UTC)")
    end_time: datetime = Field(..., description="Window end (UTC)")
    window_size_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,
        description="Width of each binned window slice in minutes.",
    )
    source_types: Optional[List[SourceType]] = Field(default=None)
    event_types: Optional[List[EventType]] = Field(default=None)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _enforce_utc(cls, v: Any) -> Any:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError("Naive datetime rejected — provide UTC-aware datetime")
        return v


class MaterializeJobResponse(BaseModel):
    """Immediate 202 response for POST /api/v1/playback/materialize."""

    job_id: str
    status: str = "pending"
    message: str = "Materialization job enqueued."


class WindowFrame(BaseModel):
    """One binned time-window in a materialized playback result."""

    window_start: datetime
    window_end: datetime
    event_count: int
    event_ids: List[str]
    late_arrival_count: int = 0


class PlaybackJobStatus(BaseModel):
    """Response for GET /api/v1/playback/jobs/{job_id}."""

    job_id: str
    state: str
    created_at: datetime
    updated_at: datetime
    request_summary: Optional[Dict[str, Any]] = None
    windows: Optional[List[WindowFrame]] = None
    total_events: Optional[int] = None
    total_windows: Optional[int] = None
    error: Optional[str] = None


# ── Entity track models (P3-3.4) ──────────────────────────────────────────────


class EntityTrackPoint(BaseModel):
    """A single spatial position in an entity track."""

    event_id: str
    event_time: datetime
    lon: float
    lat: float
    altitude_m: Optional[float] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class EntityTrackResponse(BaseModel):
    """Response for GET /api/v1/playback/entities/{entity_id}."""

    entity_id: str
    entity_type: str
    source: Optional[str] = None
    point_count: int
    track_points: List[EntityTrackPoint]
    time_range: Dict[str, datetime]
