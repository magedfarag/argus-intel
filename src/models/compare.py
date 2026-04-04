"""Pydantic models for the Imagery Compare Workflow (P2-3).

Covers POST /api/v1/imagery/compare — side-by-side metadata comparison of
two imagery scenes (before/after) retrieved from the event store.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.models.imagery import ImageryItemSummary


class ImageryCompareRequest(BaseModel):
    """POST /api/v1/imagery/compare request body."""

    before_event_id: str = Field(
        ...,
        description="event_id of the *before* (older) imagery scene.",
    )
    after_event_id: str = Field(
        ...,
        description="event_id of the *after* (newer) imagery scene.",
    )


class ImageryQualityAssessment(BaseModel):
    """Derived quality assessment of a before/after imagery pair."""

    rating: str = Field(
        ...,
        description="Overall pair quality: 'good' | 'acceptable' | 'poor'",
    )
    temporal_gap_days: float = Field(
        ...,
        description="Calendar days between after.event_time and before.event_time.",
    )
    cloud_cover_before: Optional[float] = Field(
        default=None, description="Cloud cover % for the before scene."
    )
    cloud_cover_after: Optional[float] = Field(
        default=None, description="Cloud cover % for the after scene."
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Human-readable quality notes (warnings, caveats).",
    )


class ImageryCompareResponse(BaseModel):
    """Response for POST /api/v1/imagery/compare."""

    comparison_id: str = Field(
        ...,
        description="Deterministic id derived from before+after event ids.",
    )
    before_scene: ImageryItemSummary
    after_scene: ImageryItemSummary
    quality: ImageryQualityAssessment
