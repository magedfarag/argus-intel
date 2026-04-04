"""Absence-As-Signal entity models — Phase 5 Track D.

Absence-as-signal: the *absence* of expected signals (AIS transmissions,
GPS pings, camera frames, scheduled-but-missing events) is itself a
meaningful intelligence signal.

All datetime fields MUST be UTC-aware (tzinfo != None).
signal_id and alert_id are auto-generated UUIDs.

Pydantic v2 is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# UTC helper
# ──────────────────────────────────────────────────────────────────────────────


def _require_utc(v: Any) -> Any:
    """Validate that datetime values carry explicit UTC timezone info."""
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
# Enumerations
# ──────────────────────────────────────────────────────────────────────────────


class AbsenceSignalType(str, Enum):
    """Source family of the absence detection."""

    AIS_GAP = "ais_gap"                        # vessel stops broadcasting AIS
    GPS_DENIAL = "gps_denial"                  # GPS signal loss in an area
    CAMERA_SILENCE = "camera_silence"          # camera feed goes dark
    EXPECTED_MISSING = "expected_missing"      # entity expected per schedule, not present
    COMM_BLACKOUT = "comm_blackout"            # general comms blackout in area
    TRACK_TERMINATION = "track_termination"    # track ends without conclusion


class AbsenceSeverity(str, Enum):
    """Analyst-relevant severity classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ──────────────────────────────────────────────────────────────────────────────
# Core entities
# ──────────────────────────────────────────────────────────────────────────────


class AbsenceSignal(BaseModel):
    """A single detected absence (gap, silence, or missing expected event)."""

    signal_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique signal identifier (UUID).",
    )
    signal_type: AbsenceSignalType
    entity_id: Optional[str] = Field(
        default=None,
        description="Vessel MMSI, aircraft callsign, camera ID, etc.",
    )
    entity_type: Optional[str] = Field(
        default=None,
        description="One of: vessel | aircraft | camera | area.",
    )
    aoi_geometry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON geometry dict representing the affected area.",
    )
    gap_start: datetime = Field(description="UTC-aware start of the absence window.")
    gap_end: Optional[datetime] = Field(
        default=None,
        description="UTC-aware end of the absence window; None means ongoing.",
    )
    expected_interval_seconds: Optional[float] = Field(
        default=None,
        description="How often the signal was expected, in seconds.",
    )
    last_known_value: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Last known entity state before absence began (entity-specific).",
    )
    severity: AbsenceSeverity
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence [0, 1].")
    detection_method: str = Field(
        description="E.g. 'gap_detection', 'schedule_miss', 'feed_monitor'."
    )
    provenance: Dict[str, Any] = Field(
        description="Source name, detection_timestamp, and any other provenance fields."
    )
    notes: Optional[str] = None
    related_event_ids: List[str] = Field(
        default_factory=list,
        description="Linked canonical event IDs.",
    )
    resolved: bool = False

    @field_validator("gap_start", "gap_end", mode="before")
    @classmethod
    def _require_utc(cls, v: Any) -> Any:
        return _require_utc(v)


class AbsenceSignalCreateRequest(BaseModel):
    """Inbound payload for manually creating an absence signal."""

    signal_type: AbsenceSignalType
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    aoi_geometry: Optional[Dict[str, Any]] = None
    gap_start: datetime
    gap_end: Optional[datetime] = None
    expected_interval_seconds: Optional[float] = None
    severity: AbsenceSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    detection_method: str
    provenance: Dict[str, Any]
    notes: Optional[str] = None

    @field_validator("gap_start", "gap_end", mode="before")
    @classmethod
    def _require_utc(cls, v: Any) -> Any:
        return _require_utc(v)


# ──────────────────────────────────────────────────────────────────────────────
# Derived alert
# ──────────────────────────────────────────────────────────────────────────────


class AbsenceAlert(BaseModel):
    """Derived alert aggregated from one or more correlated absence signals."""

    alert_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique alert identifier (UUID).",
    )
    title: str
    signals: List[str] = Field(description="Signal IDs contributing to this alert.")
    severity: AbsenceSeverity
    area_description: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_actions: List[str] = Field(default_factory=list)

    @field_validator("created_at", mode="before")
    @classmethod
    def _require_utc(cls, v: Any) -> Any:
        return _require_utc(v)


# ──────────────────────────────────────────────────────────────────────────────
# Analytics summary
# ──────────────────────────────────────────────────────────────────────────────


class AbsenceAnalyticsSummary(BaseModel):
    """Aggregated absence analytics over a configurable time window."""

    window_start: datetime
    window_end: datetime
    total_signals: int
    by_type: Dict[str, int] = Field(
        description="AbsenceSignalType value → count."
    )
    by_severity: Dict[str, int] = Field(
        description="AbsenceSeverity value → count."
    )
    active_signals: int = Field(description="Signals with gap_end == None.")
    resolved_signals: int = Field(description="Signals with gap_end != None.")
    high_confidence_count: int = Field(description="Signals with confidence >= 0.7.")

    @field_validator("window_start", "window_end", mode="before")
    @classmethod
    def _require_utc(cls, v: Any) -> Any:
        return _require_utc(v)
