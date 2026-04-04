"""Request/response models for the event search API (P1-4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.models.canonical_event import CanonicalEvent, EventType, SourceType


class EventSearchRequest(BaseModel):
    """POST /api/v1/events/search request body."""
    geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON Polygon/MultiPolygon AOI filter. Omit for global query (use with caution).",
    )
    aoi_id: Optional[str] = Field(
        default=None,
        description="Filter events correlated to this AOI id (correlation_keys.aoi_ids).",
    )
    start_time: datetime = Field(..., description="Window start (UTC)")
    end_time: datetime = Field(..., description="Window end (UTC)")
    event_types: Optional[List[EventType]] = Field(
        default=None,
        description="Restrict results to these event families. Omit for all families.",
    )
    source_types: Optional[List[SourceType]] = Field(
        default=None,
        description="Restrict results to these source categories.",
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Restrict results to specific connector identifiers, e.g. ['copernicus-cdse'].",
    )
    viewport_bbox: Optional[List[float]] = Field(
        default=None,
        description="Spatial viewport filter [west, south, east, north] in EPSG:4326. Optional. Delegates to TelemetryStore.query_viewport() when provided.",
    )
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class TimelineBucket(BaseModel):
    """One time-bucket entry for the timeline bar-chart API."""
    bucket_start: datetime
    bucket_end: datetime
    count: int
    by_type: Dict[str, int] = Field(default_factory=dict)


class EventSearchResponse(BaseModel):
    """Response for POST /api/v1/events/search."""
    events: List[CanonicalEvent]
    total: int
    page: int = 1
    page_size: int = 100
    has_next: bool = False
    was_reduced: bool = Field(
        default=False,
        description="P5-1.5: True when server-side density reduction was applied.",
    )


class TimelineResponse(BaseModel):
    """Response for GET /api/v1/events/timeline."""
    buckets: List[TimelineBucket]
    total_events: int
    bucket_size_minutes: int


class SourceSummary(BaseModel):
    """One entry in the active sources list."""
    connector_id: str
    display_name: str
    source_type: str
    event_count: int = 0
    last_event_time: Optional[datetime] = None
