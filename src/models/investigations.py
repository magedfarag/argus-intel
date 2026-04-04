"""Investigation entity model — Phase 5 Track A.

Provides the Pydantic v2 models for saved investigations, watchlists,
analyst notes, saved filters, and evidence linking.

All datetime fields are UTC-aware.  IDs are auto-generated UUIDs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.operational_layers import EvidenceLink


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────


class InvestigationStatus(str, Enum):
    """Lifecycle states for an investigation."""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class WatchlistEntryType(str, Enum):
    """Entity categories that can be added to an investigation watchlist."""
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"
    LOCATION = "location"
    EVENT_PATTERN = "event_pattern"
    PERSON = "person"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_utc(v: Any) -> Any:
    """Validate that a datetime value is UTC-aware."""
    if v is None:
        return v
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if isinstance(v, datetime) and v.tzinfo is None:
        raise ValueError(
            f"Naive datetime rejected — all timestamps must carry UTC timezone info: {v!r}"
        )
    return v


# ──────────────────────────────────────────────────────────────────────────────
# Sub-models
# ──────────────────────────────────────────────────────────────────────────────


class WatchlistEntry(BaseModel):
    """A single entity under active monitoring within an investigation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    entry_type: WatchlistEntryType
    identifier: str = Field(..., description="MMSI, ICAO hex, lat/lon pair, etc.")
    label: Optional[str] = Field(default=None, description="Human-readable display name")
    notes: Optional[str] = Field(default=None)
    added_at: datetime = Field(default_factory=_utc_now)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("added_at", mode="before")
    @classmethod
    def _utc_added_at(cls, v: Any) -> Any:
        return _require_utc(v)


class InvestigationNote(BaseModel):
    """A free-text analyst note attached to an investigation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    investigation_id: str
    content: str
    author: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    tags: List[str] = Field(default_factory=list)

    @field_validator("created_at", mode="before")
    @classmethod
    def _utc_created_at(cls, v: Any) -> Any:
        return _require_utc(v)


class SavedFilter(BaseModel):
    """A named query filter captured for reuse inside an investigation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    filter_definition: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary JSON filter parameters, e.g. event_types, aoi_id, time_range",
    )
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("created_at", mode="before")
    @classmethod
    def _utc_created_at(cls, v: Any) -> Any:
        return _require_utc(v)


# ──────────────────────────────────────────────────────────────────────────────
# Core entity
# ──────────────────────────────────────────────────────────────────────────────


class Investigation(BaseModel):
    """Top-level investigation entity — the analyst's workspace."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    status: InvestigationStatus = InvestigationStatus.DRAFT
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    created_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    watchlist: List[WatchlistEntry] = Field(default_factory=list)
    notes: List[InvestigationNote] = Field(default_factory=list)
    saved_filters: List[SavedFilter] = Field(default_factory=list)
    evidence_links: List[EvidenceLink] = Field(default_factory=list)
    linked_event_ids: List[str] = Field(
        default_factory=list,
        description="Canonical event_id values associated with this investigation",
    )

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _utc_timestamps(cls, v: Any) -> Any:
        return _require_utc(v)

    @model_validator(mode="after")
    def _updated_at_gte_created_at(self) -> "Investigation":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────────────────────


class InvestigationCreateRequest(BaseModel):
    """Payload for creating a new investigation."""

    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class InvestigationUpdateRequest(BaseModel):
    """Partial-update payload — all fields optional."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[InvestigationStatus] = None
    tags: Optional[List[str]] = None


class InvestigationListResponse(BaseModel):
    """Paginated list of investigations."""

    items: List[Investigation]
    total: int


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

__all__ = [
    "InvestigationStatus",
    "WatchlistEntryType",
    "WatchlistEntry",
    "InvestigationNote",
    "SavedFilter",
    "Investigation",
    "InvestigationCreateRequest",
    "InvestigationUpdateRequest",
    "InvestigationListResponse",
]
