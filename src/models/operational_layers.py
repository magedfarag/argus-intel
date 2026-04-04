"""Operational-layer event models for Phase 2 of the ARGUS WorldView Transformation.

These models cover:
  - Satellite orbit and pass prediction (Track A)
  - Airspace restrictions and NOTAMs (Track B)
  - GPS jamming detection (Track C)
  - Strike / battle-damage reconstruction (Track D)
  - Evidence linking (cross-cutting)

All datetime fields MUST be UTC-aware (tzinfo != None).  Pass
``datetime.now(timezone.utc)`` or ``datetime.fromisoformat("...+00:00")``
— never naive datetimes.

Pydantic v2 is required.  Validators use ``model_validator(mode='after')``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _require_utc(v: Any) -> Any:
    """Shared UTC-aware validator used across models."""
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
# Track A — Satellite Orbit & Pass
# ──────────────────────────────────────────────────────────────────────────────


class SatelliteOrbit(BaseModel):
    """Current orbital parameters for a satellite, populated from a TLE or similar source.

    ``loaded_at`` records when this record was ingested; it must be UTC-aware.
    """

    satellite_id: str = Field(..., description="Canonical satellite identifier, e.g. 'SENTINEL-2A'")
    norad_id: Optional[int] = Field(default=None, description="NORAD catalogue number")
    tle_line1: Optional[str] = Field(default=None, description="First line of two-line element set")
    tle_line2: Optional[str] = Field(default=None, description="Second line of two-line element set")
    orbital_period_minutes: Optional[float] = Field(default=None, gt=0.0)
    inclination_deg: Optional[float] = Field(default=None, ge=0.0, le=180.0)
    altitude_km: Optional[float] = Field(default=None, gt=0.0)
    source: str = Field(..., description="Data provider, e.g. 'space-track.org'")
    loaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC-aware timestamp when this record was loaded",
    )

    @field_validator("loaded_at", mode="before")
    @classmethod
    def _utc_loaded_at(cls, v: Any) -> Any:
        return _require_utc(v)


class SatellitePass(BaseModel):
    """A predicted or observed overpass of a satellite above an area of interest.

    ``aos`` (acquisition of signal) and ``los`` (loss of signal) delimit the
    observable window.  Both must be UTC-aware.
    ``confidence`` represents certainty of the prediction (default 1.0 for
    deterministic TLE-derived predictions).
    """

    satellite_id: str = Field(..., description="Canonical satellite identifier")
    norad_id: Optional[int] = Field(default=None)
    aos: datetime = Field(..., description="Acquisition-of-signal timestamp (UTC)")
    los: datetime = Field(..., description="Loss-of-signal timestamp (UTC)")
    max_elevation_deg: Optional[float] = Field(default=None, ge=0.0, le=90.0)
    footprint_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON Polygon describing ground track / sensor footprint",
    )
    sensor_type: Optional[str] = Field(
        default=None, description="e.g. 'MSI', 'SAR', 'optical'"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(..., description="Data provider or prediction service")

    @field_validator("aos", "los", mode="before")
    @classmethod
    def _utc_timestamps(cls, v: Any) -> Any:
        return _require_utc(v)

    @field_validator("footprint_geojson")
    @classmethod
    def _validate_geojson(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if "type" not in v or "coordinates" not in v:
            raise ValueError("footprint_geojson must be a GeoJSON object with 'type' and 'coordinates'")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.aos >= self.los:
            raise ValueError("aos must be strictly before los")


# ──────────────────────────────────────────────────────────────────────────────
# Track B — Airspace Restrictions & NOTAMs
# ──────────────────────────────────────────────────────────────────────────────


class AirspaceRestriction(BaseModel):
    """A geometric airspace restriction — TFR, MOA, NFZ, etc.

    ``valid_to=None`` means the restriction is indefinite.
    ``geometry_geojson`` must be a valid GeoJSON Polygon or MultiPolygon.
    All datetime fields must be UTC-aware.
    """

    restriction_id: str = Field(..., description="Canonical identifier for this restriction")
    name: str = Field(..., description="Human-readable name, e.g. 'RIYADH TFR 2026-04'")
    restriction_type: str = Field(
        ..., description="Restriction category: 'TFR', 'MOA', 'NFZ', 'ADIZ', 'CTR', etc."
    )
    geometry_geojson: Dict[str, Any] = Field(
        ..., description="GeoJSON Polygon or MultiPolygon defining the restricted area"
    )
    lower_limit_ft: Optional[float] = Field(default=None, description="Lower altitude limit in feet MSL")
    upper_limit_ft: Optional[float] = Field(default=None, description="Upper altitude limit in feet MSL")
    valid_from: datetime = Field(..., description="Activation timestamp (UTC)")
    valid_to: Optional[datetime] = Field(
        default=None, description="Deactivation timestamp (UTC); None = indefinite"
    )
    is_active: bool = Field(default=True)
    source: str = Field(..., description="Data provider, e.g. 'FAA', 'NOTAM-feed'")
    provenance: Optional[str] = Field(
        default=None, description="Raw source reference or URL"
    )

    @field_validator("valid_from", "valid_to", mode="before")
    @classmethod
    def _utc_validity(cls, v: Any) -> Any:
        return _require_utc(v)

    @field_validator("geometry_geojson")
    @classmethod
    def _validate_geojson(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if "type" not in v or "coordinates" not in v:
            raise ValueError("geometry_geojson must be a GeoJSON object with 'type' and 'coordinates'")
        return v


class NotamEvent(BaseModel):
    """A Notice to Airmen (NOTAM) event.

    ``effective_to=None`` means the NOTAM is open-ended.
    ``geometry_geojson`` is optional; not all NOTAMs carry geometric bounds.
    All datetime fields must be UTC-aware.
    """

    notam_id: str = Field(..., description="Canonical internal identifier")
    notam_number: str = Field(..., description="Official NOTAM number, e.g. 'A1234/26'")
    subject: str = Field(..., description="NOTAM subject or Q-code subject, e.g. 'Airspace restriction'")
    condition: str = Field(..., description="NOTAM condition description")
    location_icao: Optional[str] = Field(
        default=None, description="ICAO location indicator, e.g. 'OEJD'"
    )
    effective_from: datetime = Field(..., description="Effective start timestamp (UTC)")
    effective_to: Optional[datetime] = Field(
        default=None, description="Effective end timestamp (UTC); None = open-ended"
    )
    geometry_geojson: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional GeoJSON geometry scoping the NOTAM"
    )
    raw_text: Optional[str] = Field(default=None, description="Full raw NOTAM text")
    source: str = Field(..., description="Data provider or feed identifier")

    @field_validator("effective_from", "effective_to", mode="before")
    @classmethod
    def _utc_effective(cls, v: Any) -> Any:
        return _require_utc(v)

    @field_validator("geometry_geojson")
    @classmethod
    def _validate_geojson(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if "type" not in v or "coordinates" not in v:
            raise ValueError("geometry_geojson must be a GeoJSON object with 'type' and 'coordinates'")
        return v


# ──────────────────────────────────────────────────────────────────────────────
# Track C — GPS Jamming
# ──────────────────────────────────────────────────────────────────────────────


class GpsJammingEvent(BaseModel):
    """A detected GPS / GNSS jamming or spoofing event.

    ``detection_method`` distinguishes between algorithmically derived signals,
    field reports, and independently confirmed events — critical for downstream
    fusion and confidence weighting.
    ``provenance`` is mandatory to ensure source-chain traceability.
    All datetime fields must be UTC-aware.
    """

    DETECTION_METHODS: ClassVar[set] = {"derived", "reported", "confirmed"}

    jamming_id: str = Field(..., description="Canonical identifier, deterministic from source+time+location")
    detected_at: datetime = Field(..., description="Detection or report timestamp (UTC)")
    location_lon: float = Field(..., ge=-180.0, le=180.0)
    location_lat: float = Field(..., ge=-90.0, le=90.0)
    radius_km: Optional[float] = Field(default=None, gt=0.0, description="Estimated affected radius in km")
    affected_area_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional GeoJSON Polygon defining affected area (preferred over radius_km when available)",
    )
    jamming_type: str = Field(
        default="unknown",
        description="Classification: 'jamming', 'spoofing', 'interference', 'unknown'",
    )
    signal_strength_db: Optional[float] = Field(
        default=None, description="Observed jamming signal strength in dBm"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(..., description="Data provider or detection system")
    provenance: str = Field(..., description="Raw source reference, URL, or report identifier")
    detection_method: str = Field(
        default="derived",
        description="How the event was determined: 'derived' | 'reported' | 'confirmed'",
    )

    @field_validator("detected_at", mode="before")
    @classmethod
    def _utc_detected(cls, v: Any) -> Any:
        return _require_utc(v)

    @field_validator("affected_area_geojson")
    @classmethod
    def _validate_geojson(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if "type" not in v or "coordinates" not in v:
            raise ValueError("affected_area_geojson must be a GeoJSON object with 'type' and 'coordinates'")
        return v

    @field_validator("detection_method")
    @classmethod
    def _validate_detection_method(cls, v: str) -> str:
        allowed = {"derived", "reported", "confirmed"}
        if v not in allowed:
            raise ValueError(f"detection_method must be one of {allowed!r}, got {v!r}")
        return v


# ──────────────────────────────────────────────────────────────────────────────
# Track D — Strike / Battle-Damage Reconstruction
# ──────────────────────────────────────────────────────────────────────────────


class StrikeEvent(BaseModel):
    """A reported or reconstructed strike event (airstrike, artillery, missile, etc.).

    Designed for multi-source corroboration workflows.  ``corroboration_count``
    tracks how many independent sources confirm the event; fusion pipelines
    should increment this as new evidence arrives.
    ``evidence_refs`` holds canonical ``evidence_id`` values from ``EvidenceLink``.
    ``provenance`` is mandatory; strikes are high-stakes events and source
    traceability is non-negotiable.
    All datetime fields must be UTC-aware.
    """

    strike_id: str = Field(..., description="Canonical identifier, deterministic from source+location+time")
    occurred_at: datetime = Field(..., description="Estimated or reported occurrence timestamp (UTC)")
    location_lon: float = Field(..., ge=-180.0, le=180.0)
    location_lat: float = Field(..., ge=-90.0, le=90.0)
    location_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional GeoJSON geometry (point, polygon, or impact crater outline)",
    )
    strike_type: str = Field(
        default="unknown",
        description="Strike category: 'airstrike', 'artillery', 'missile', 'drone', 'unknown'",
    )
    target_description: Optional[str] = Field(
        default=None, description="Human-readable description of the presumed target"
    )
    damage_severity: Optional[str] = Field(
        default=None,
        description="Assessed damage severity: 'none', 'minor', 'moderate', 'severe', 'destroyed'",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="List of canonical evidence_id values from EvidenceLink",
    )
    source: str = Field(..., description="Primary data provider or analyst identifier")
    provenance: str = Field(..., description="Raw source reference, URL, or report identifier")
    corroboration_count: int = Field(
        default=0,
        ge=0,
        description="Number of independent sources corroborating this event",
    )

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _utc_occurred(cls, v: Any) -> Any:
        return _require_utc(v)

    @field_validator("location_geojson")
    @classmethod
    def _validate_geojson(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if "type" not in v or "coordinates" not in v:
            raise ValueError("location_geojson must be a GeoJSON object with 'type' and 'coordinates'")
        return v


# ──────────────────────────────────────────────────────────────────────────────
# Cross-cutting — Evidence Linking
# ──────────────────────────────────────────────────────────────────────────────


class EvidenceLink(BaseModel):
    """Links a piece of evidence to a canonical event for investigation workflows.

    Supports multi-source corroboration: attach imagery, AIS records, OSINT
    reports, or any other artefact to any event type via ``event_id``.
    ``added_at`` must be UTC-aware — it records when the link was created, not
    when the evidence was generated.
    """

    evidence_id: str = Field(..., description="Unique identifier for this evidence record")
    event_id: str = Field(..., description="Canonical event_id of the associated event")
    evidence_type: str = Field(
        ...,
        description="Evidence category: 'imagery', 'ais_record', 'report', 'adsb_record', 'social_media', etc.",
    )
    url: Optional[str] = Field(default=None, description="URL to the evidence artefact if publicly accessible")
    description: Optional[str] = Field(default=None, description="Human-readable description of the evidence")
    added_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC-aware timestamp when this link was created",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Analyst confidence that this evidence relates to the cited event",
    )

    @field_validator("added_at", mode="before")
    @classmethod
    def _utc_added_at(cls, v: Any) -> Any:
        return _require_utc(v)
