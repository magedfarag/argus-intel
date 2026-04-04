"""Canonical event model — single normalized envelope for all source families.

Implements the schema defined in docs/geoint-platform-architecture-and-plan/
schemas/canonical-event.schema.json and the design goals in
docs/geoint-platform-architecture-and-plan/docs/canonical-event-model.md.

All timestamps MUST be UTC-aware (ISO 8601 with Z or +00:00 offset).
Confidence scores are in [0.0, 1.0].
event_id is deterministic: generate with make_event_id().
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations (P0-3.2)
# ──────────────────────────────────────────────────────────────────────────────


class EventType(str, Enum):
    """All supported event families."""
    IMAGERY_ACQUISITION = "imagery_acquisition"
    IMAGERY_DETECTION = "imagery_detection"
    CHANGE_DETECTION = "change_detection"
    SHIP_POSITION = "ship_position"
    SHIP_TRACK_SEGMENT = "ship_track_segment"
    AIRCRAFT_POSITION = "aircraft_position"
    AIRCRAFT_TRACK_SEGMENT = "aircraft_track_segment"
    PERMIT_EVENT = "permit_event"
    INSPECTION_EVENT = "inspection_event"
    PROJECT_EVENT = "project_event"
    COMPLAINT_EVENT = "complaint_event"
    CONTEXTUAL_EVENT = "contextual_event"
    SYSTEM_HEALTH_EVENT = "system_health_event"
    DARK_SHIP_CANDIDATE = "dark_ship_candidate"
    SATELLITE_PASS = "satellite_pass"
    SATELLITE_ORBIT = "satellite_orbit"
    AIRSPACE_RESTRICTION = "airspace_restriction"
    NOTAM_EVENT = "notam_event"
    GPS_JAMMING_EVENT = "gps_jamming_event"
    STRIKE_EVENT = "strike_event"
    CAMERA_OBSERVATION = "camera_observation"
    DETECTION_OVERLAY = "detection_overlay"
    VIDEO_CLIP_REF = "video_clip_ref"
    RENDER_MODE_EVENT = "render_mode_event"


class SourceType(str, Enum):
    """Normalised source category codes."""
    IMAGERY_CATALOG = "imagery_catalog"
    TELEMETRY = "telemetry"
    REGISTRY = "registry"
    PUBLIC_RECORD = "public_record"
    CONTEXT_FEED = "context_feed"
    DERIVED = "derived"


class EntityType(str, Enum):
    """The kind of real-world object an event is about."""
    IMAGERY_SCENE = "imagery_scene"
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"
    CONSTRUCTION_SITE = "construction_site"
    PERMIT = "permit"
    NEWS_ARTICLE = "news_article"
    SYSTEM = "system"
    TRACK = "track"


# ──────────────────────────────────────────────────────────────────────────────
# Sub-models (P0-3.3)
# ──────────────────────────────────────────────────────────────────────────────


class NormalizationRecord(BaseModel):
    """Tracks how and when raw source data was transformed."""
    schema_version: str = Field(default="1.0.0")
    normalized_by: str = Field(..., description="Connector module identifier, e.g. connector.cdse.stac")
    normalization_warnings: List[str] = Field(default_factory=list)
    dedupe_key: Optional[str] = Field(default=None)


class ProvenanceRecord(BaseModel):
    """Links back to the raw source artefact."""
    raw_source_ref: str = Field(..., description="S3 path or equivalent reference to the raw payload")
    source_record_id: Optional[str] = Field(default=None)
    source_record_version: Optional[str] = Field(default=None, description="ETag or content-hash of the source record")
    source_url: Optional[str] = Field(default=None)


class LicenseRecord(BaseModel):
    """Per-event licensing and redistribution metadata."""
    access_tier: str = Field(default="public", description="public | restricted | commercial")
    commercial_use: str = Field(default="check-provider-terms", description="allowed | allowed-with-terms | not-allowed | check-provider-terms")
    redistribution: str = Field(default="check-provider-terms", description="allowed | not-allowed | check-provider-terms")
    attribution_required: bool = Field(default=True)


class CorrelationKeys(BaseModel):
    """Typed cross-reference pointers for entity-centric correlation."""
    aoi_ids: List[str] = Field(default_factory=list)
    mmsi: Optional[str] = Field(default=None, description="Maritime Mobile Service Identity")
    imo: Optional[str] = Field(default=None, description="IMO vessel number")
    icao24: Optional[str] = Field(default=None, description="ICAO 24-bit aircraft address")
    callsign: Optional[str] = Field(default=None)
    permit_id: Optional[str] = Field(default=None)
    place_key: Optional[str] = Field(default=None, description="Normalised place identifier, e.g. SA-RIYADH")


# ──────────────────────────────────────────────────────────────────────────────
# Per-family attribute models (P0-3.4)
# ──────────────────────────────────────────────────────────────────────────────


class ImageryAttributes(BaseModel):
    """Attributes for imagery_acquisition and imagery_detection events."""
    platform: Optional[str] = Field(default=None, description="e.g. Sentinel-2A, Landsat-9")
    sensor: Optional[str] = Field(default=None)
    gsd_m: Optional[float] = Field(default=None, description="Ground sample distance in metres")
    cloud_cover_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    off_nadir_angle: Optional[float] = Field(default=None)
    sun_azimuth: Optional[float] = Field(default=None)
    scene_url: Optional[str] = Field(default=None)
    bands_available: List[str] = Field(default_factory=list)
    processing_level: Optional[str] = Field(default=None, description="e.g. L1C, L2A, ARD")


class ShipPositionAttributes(BaseModel):
    """Attributes for ship_position events."""
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    ship_type: Optional[int] = None
    course_deg: Optional[float] = Field(default=None, ge=0.0, le=360.0)
    speed_kn: Optional[float] = Field(default=None, ge=0.0)
    heading_deg: Optional[float] = Field(default=None, ge=0.0, le=360.0)
    nav_status: Optional[str] = None
    length_m: Optional[float] = None
    beam_m: Optional[float] = None
    destination: Optional[str] = None
    eta: Optional[str] = None


class AircraftAttributes(BaseModel):
    """Attributes for aircraft_position events."""
    icao24: Optional[str] = None
    callsign: Optional[str] = None
    origin_country: Optional[str] = None
    baro_altitude_m: Optional[float] = None
    geo_altitude_m: Optional[float] = None
    velocity_ms: Optional[float] = None
    true_track_deg: Optional[float] = None
    vertical_rate_ms: Optional[float] = None
    on_ground: Optional[bool] = None
    squawk: Optional[str] = None


class PermitAttributes(BaseModel):
    """Attributes for permit_event events."""
    permit_number: Optional[str] = None
    permit_type: Optional[str] = None
    applicant: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    authority: Optional[str] = None


class ContextualAttributes(BaseModel):
    """Attributes for contextual_event events derived from GDELT and similar feeds."""
    headline: Optional[str] = None
    url: Optional[str] = None
    tone: Optional[float] = None
    theme_codes: List[str] = Field(default_factory=list)
    source_publication: Optional[str] = None
    language: Optional[str] = None
    num_mentions: Optional[int] = None
    num_sources: Optional[int] = None
    gdelt_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Main canonical event model (P0-3.1)
# ──────────────────────────────────────────────────────────────────────────────


class CanonicalEvent(BaseModel):
    """Single normalised envelope for all geospatial event families.

    Designed for storage in PostgreSQL/PostGIS canonical_events table.
    geometry and centroid conform to GeoJSON (RFC 7946).

    Usage::
        event = CanonicalEvent(
            event_id=make_event_id("copernicus-cdse", "S2A_...", "2026-04-01T10:22:33Z"),
            source="copernicus-cdse",
            source_type=SourceType.IMAGERY_CATALOG,
            entity_type=EntityType.IMAGERY_SCENE,
            event_type=EventType.IMAGERY_ACQUISITION,
            event_time=datetime(2026, 4, 1, 10, 22, 33, tzinfo=timezone.utc),
            geometry={"type": "Polygon", "coordinates": [...]},
            centroid={"type": "Point", "coordinates": [46.67, 24.71]},
            attributes=ImageryAttributes(platform="Sentinel-2A", cloud_cover_pct=3.2).model_dump(),
            normalization=NormalizationRecord(normalized_by="connector.cdse.stac"),
            provenance=ProvenanceRecord(raw_source_ref="s3://bucket/raw/cdse/scene.json"),
            ingested_at=datetime.now(timezone.utc),
            license=LicenseRecord(),
        )
    """

    # Identity
    event_id: str = Field(..., description="Deterministic internal identifier; use make_event_id()")
    source: str = Field(..., description="Normalised provider/source code, e.g. copernicus-cdse")
    source_type: SourceType
    entity_type: EntityType
    entity_id: Optional[str] = Field(
        default=None,
        description=(
            "Source-native entity identifier. Semantics by entity_type: "
            "VESSEL → MMSI (9-digit string, zero-padded); "
            "AIRCRAFT → ICAO24 hex string; "
            "IMAGERY_SCENE → catalogue scene_id (e.g. Sentinel-2 SAFE path); "
            "CONTEXTUAL_EVENT → GDELT event_id when available, else None; "
            "PERMIT → permit_number from issuing authority."
        ),
    )
    event_type: EventType

    # Time — all UTC enforced by validator
    event_time: datetime = Field(..., description="Primary event timestamp (UTC)")
    time_start: Optional[datetime] = Field(default=None, description="Interval start (UTC)")
    time_end: Optional[datetime] = Field(default=None, description="Interval end (UTC)")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    first_seen_at: Optional[datetime] = Field(default=None)
    last_seen_at: Optional[datetime] = Field(default=None)

    # Spatial — GeoJSON dicts
    geometry: Dict[str, Any] = Field(..., description="GeoJSON geometry object (RFC 7946)")
    centroid: Dict[str, Any] = Field(..., description="GeoJSON Point at event centroid")
    altitude_m: Optional[float] = Field(default=None)
    depth_m: Optional[float] = Field(default=None)

    # Quality
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    quality_flags: List[str] = Field(default_factory=list)

    # Payload — typed per family, serialised to dict for schema flexibility
    attributes: Dict[str, Any] = Field(default_factory=dict)

    # Provenance chain
    normalization: NormalizationRecord
    provenance: ProvenanceRecord
    correlation_keys: CorrelationKeys = Field(default_factory=CorrelationKeys)
    license: LicenseRecord = Field(default_factory=LicenseRecord)

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("event_time", "time_start", "time_end", "ingested_at", "first_seen_at", "last_seen_at", mode="before")
    @classmethod
    def _enforce_utc(cls, v: Any) -> Any:
        """Reject naive datetimes; coerce Z/+00:00 strings to UTC-aware datetime."""
        if v is None:
            return v
        if isinstance(v, str):
            # Replace trailing Z with +00:00 for fromisoformat compat
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime):
            if v.tzinfo is None:
                raise ValueError(f"Naive datetime rejected — all timestamps must carry UTC timezone info: {v!r}")
            return v
        return v

    @field_validator("geometry", "centroid")
    @classmethod
    def _require_geojson_type(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if "type" not in v or "coordinates" not in v:
            raise ValueError("geometry/centroid must be a GeoJSON object with 'type' and 'coordinates'")
        return v

    @field_validator("centroid")
    @classmethod
    def _centroid_must_be_point(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if v.get("type") != "Point":
            raise ValueError("centroid must be a GeoJSON Point")
        return v

    @model_validator(mode="after")
    def _time_interval_order(self) -> "CanonicalEvent":
        if self.time_start and self.time_end and self.time_start > self.time_end:
            raise ValueError("time_start must not be after time_end")
        return self


# ──────────────────────────────────────────────────────────────────────────────
# event_id generation utility (P0-3.6)
# ──────────────────────────────────────────────────────────────────────────────


def make_event_id(source: str, entity_id: str, event_time: str | datetime) -> str:
    """Generate a deterministic event_id from (source, entity_id, event_time).

    The ID is stable: the same source+entity+time always yields the same id,
    enabling safe upserts and deduplication without external coordination.

    Args:
        source:     Normalised provider code, e.g. "copernicus-cdse".
        entity_id:  Source-native scene or object identifier.
        event_time: UTC datetime or ISO 8601 string.

    Returns:
        String of the form ``evt_<source_slug>_<sha256_12>``.

    Example::
        make_event_id("copernicus-cdse", "S2A_MSIL2A_20260401", "2026-04-01T10:22:33Z")
        # "evt_copernicus-cdse_a3f8b2c1d04e"
    """
    if isinstance(event_time, datetime):
        ts = event_time.astimezone(timezone.utc).isoformat()
    else:
        ts = event_time
    raw = f"{source}:{entity_id}:{ts}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    source_slug = source.lower().replace(" ", "-")
    return f"evt_{source_slug}_{digest}"
