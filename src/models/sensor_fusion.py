"""Sensor fusion models for Phase 4 Track B — Camera/Video Abstraction.

Covers:
  - GeoRegistration: world-anchor for a camera
  - CameraObservation: single observation event from a camera or sensor
  - MediaClipRef: reference to a stored video or image clip
  - RenderModeEvent: audit event for scene render-mode changes
  - DetectionOverlay: single object detection result linked to a camera observation

All datetime fields MUST be UTC-aware (tzinfo != None).
Pydantic v2 is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _require_utc(v: Any) -> Any:
    """Shared UTC-aware validator for all datetime fields."""
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
# Camera and geo-registration
# ──────────────────────────────────────────────────────────────────────────────


class GeoRegistration(BaseModel):
    """Georegistration anchor for a camera in the world."""

    lon: float = Field(..., description="Decimal degrees longitude")
    lat: float = Field(..., description="Decimal degrees latitude")
    altitude_m: Optional[float] = Field(
        default=None, description="Height above ground, metres"
    )
    heading_deg: float = Field(
        default=0.0, description="Camera azimuth (0=North, 90=East)"
    )
    pitch_deg: float = Field(
        default=0.0, description="Tilt from horizontal (negative = down)"
    )
    roll_deg: float = Field(default=0.0, description="Roll offset in degrees")
    fov_horizontal_deg: float = Field(
        default=90.0, description="Horizontal field of view in degrees"
    )
    fov_vertical_deg: float = Field(
        default=60.0, description="Vertical field of view in degrees"
    )
    is_mobile: bool = Field(
        default=False,
        description="True when the platform is moving (drone, vehicle)",
    )


class CameraObservation(BaseModel):
    """Single camera or sensor observation event."""

    camera_id: str
    observation_id: str
    observed_at: datetime = Field(..., description="UTC-aware timestamp of the observation")
    camera_type: str = Field(
        default="optical",
        description="optical | thermal | night_vision | radar | sar",
    )
    geo_registration: GeoRegistration
    clip_ref: Optional[str] = Field(
        default=None, description="URL or storage key to the video clip"
    )
    clip_start_offset_sec: Optional[float] = Field(
        default=None, description="Offset within the clip for this observation"
    )
    clip_duration_sec: Optional[float] = None
    thumbnail_url: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: str
    provenance: str
    tags: List[str] = Field(default_factory=list)

    @field_validator("observed_at", mode="before")
    @classmethod
    def _utc_observed_at(cls, v: Any) -> Any:
        return _require_utc(v)


class MediaClipRef(BaseModel):
    """Reference to a stored video or image clip."""

    clip_id: str
    camera_id: str
    recorded_at: datetime = Field(
        ..., description="UTC-aware start timestamp of the clip"
    )
    duration_sec: float
    url: str = Field(..., description="HTTP URL or presigned storage URL")
    media_type: str = Field(default="video/mp4")
    resolution_width: Optional[int] = None
    resolution_height: Optional[int] = None
    storage_key: Optional[str] = None
    is_loopable: bool = Field(
        default=False, description="True for simulated/demo clips"
    )
    provenance: str

    @field_validator("recorded_at", mode="before")
    @classmethod
    def _utc_recorded_at(cls, v: Any) -> Any:
        return _require_utc(v)


# ──────────────────────────────────────────────────────────────────────────────
# Render mode audit
# ──────────────────────────────────────────────────────────────────────────────


class RenderModeEvent(BaseModel):
    """Audit event when the scene render mode changes."""

    event_id: str
    occurred_at: datetime = Field(..., description="UTC-aware timestamp")
    from_mode: str = Field(
        ..., description="day | low_light | night_vision | thermal"
    )
    to_mode: str
    triggered_by: str = Field(
        default="user", description="user | auto | playback"
    )

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _utc_occurred_at(cls, v: Any) -> Any:
        return _require_utc(v)


# ──────────────────────────────────────────────────────────────────────────────
# Detection overlay (Track D)
# ──────────────────────────────────────────────────────────────────────────────


class DetectionOverlay(BaseModel):
    """Single object detection result linked to a camera observation."""

    detection_id: str
    observation_id: str = Field(
        ..., description="Links to CameraObservation.observation_id"
    )
    detected_at: datetime = Field(..., description="UTC-aware timestamp")
    detection_type: str = Field(
        ...,
        description="vehicle | person | aircraft | vessel | infrastructure | unknown",
    )
    bounding_box: Optional[Dict[str, float]] = Field(
        default=None,
        description="{x, y, width, height} in clip-relative 0-1 coordinates",
    )
    geo_location: Optional[Dict[str, float]] = Field(
        default=None,
        description="{lon, lat, altitude_m} — None if not georegistered",
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    model_version: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)
    source: str
    provenance: str

    @field_validator("detected_at", mode="before")
    @classmethod
    def _utc_detected_at(cls, v: Any) -> Any:
        return _require_utc(v)
