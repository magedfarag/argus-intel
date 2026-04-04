"""SQLAlchemy ORM models — PostGIS schema (P0-4.1).

Tables:
  aois                — analyst-defined areas of interest  (P0-4.3)
  canonical_events    — normalised event envelope (all source families)
  track_segments      — pre-computed vessel/aircraft track segments
  source_metadata     — source health + freshness per connector  (P0-5.4)
  analyst_annotations — analyst verdict + notes on change candidates

All geometry columns use EPSG:4326 (WGS-84) via GeoAlchemy2.
All timestamps are stored as TIMESTAMPTZ (UTC-aware).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

try:
    from geoalchemy2 import Geometry  # type: ignore[import-untyped]
    _GEO_AVAILABLE = True
except ImportError:
    # GeoAlchemy2 not installed — use a plain JSON column fallback for dev/CI
    Geometry = None  # type: ignore[assignment,misc]
    _GEO_AVAILABLE = False


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── aois ──────────────────────────────────────────────────────────────────────


class AOI(Base):
    """Analyst-defined area of interest (P0-4.3).

    Every search, replay, and export is scoped to one AOI.
    """
    __tablename__ = "aois"

    id = Column(String(36), primary_key=True, comment="UUID")
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    # GeoJSON Polygon/MultiPolygon stored as PostGIS geometry (EPSG:4326)
    geometry = Column(
        Geometry("GEOMETRY", srid=4326) if _GEO_AVAILABLE else JSONB,
        nullable=False,
    )
    tags = Column(JSONB, nullable=False, default=list)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    deleted = Column(Boolean, nullable=False, default=False, index=True)

    # Relationships
    events = relationship("CanonicalEventRow", back_populates="aoi", lazy="dynamic")
    annotations = relationship("AnalystAnnotation", back_populates="aoi", lazy="dynamic")

    __table_args__ = (
        Index("ix_aois_deleted_created", "deleted", "created_at"),
    )


# ── canonical_events ──────────────────────────────────────────────────────────


class CanonicalEventRow(Base):
    """Persistent canonical event envelope (P0-4.1).

    event_id is deterministic (SHA-256 of source+entity_id+event_time),
    enabling safe upserts without coordination.
    """
    __tablename__ = "canonical_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(128), nullable=False, unique=True, index=True, comment="Deterministic SHA-256 ID")
    source = Column(String(128), nullable=False, index=True)
    source_type = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(256), nullable=True)
    event_type = Column(String(64), nullable=False, index=True)
    event_time = Column(DateTime(timezone=True), nullable=False, index=True)
    time_start = Column(DateTime(timezone=True), nullable=True)
    time_end = Column(DateTime(timezone=True), nullable=True)
    # Geometry + centroid
    geometry = Column(
        Geometry("GEOMETRY", srid=4326) if _GEO_AVAILABLE else JSONB,
        nullable=True,
    )
    centroid = Column(
        Geometry("POINT", srid=4326) if _GEO_AVAILABLE else JSONB,
        nullable=True,
    )
    altitude_m = Column(Float, nullable=True)
    # Metadata JSONB columns
    attributes = Column(JSONB, nullable=False, default=dict)
    normalization = Column(JSONB, nullable=True)
    provenance = Column(JSONB, nullable=True)
    license_ = Column("license", JSONB, nullable=True)
    correlation_keys = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=True)
    quality_flags = Column(JSONB, nullable=False, default=list)
    tags = Column(JSONB, nullable=False, default=list)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    # FK to primary AOI for fast intersection queries
    # Nullable — events without any AOI association are valid
    primary_aoi_id = Column(String(36), ForeignKey("aois.id", ondelete="SET NULL"), nullable=True, index=True)

    aoi = relationship("AOI", back_populates="events")

    __table_args__ = (
        # Composite index optimised for AOI+time window queries (P0-4.2)
        Index("ix_events_time_source_entity", "event_time", "source", "entity_type"),
        Index("ix_events_aoi_time", "primary_aoi_id", "event_time"),
    )


# ── track_segments ────────────────────────────────────────────────────────────


class TrackSegment(Base):
    """Pre-computed vessel or aircraft track segment.

    A track segment aggregates sequential position events for one entity
    into a linestring geometry. Materialised by the track builder service.
    """
    __tablename__ = "track_segments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_id = Column(String(256), nullable=False, index=True, comment="MMSI, ICAO24, etc.")
    entity_type = Column(String(64), nullable=False, index=True, comment="vessel | aircraft")
    source = Column(String(128), nullable=False)
    segment_start = Column(DateTime(timezone=True), nullable=False, index=True)
    segment_end = Column(DateTime(timezone=True), nullable=False)
    point_count = Column(Integer, nullable=False, default=0)
    distance_km = Column(Float, nullable=True)
    avg_speed_kn = Column(Float, nullable=True)
    track_geom = Column(
        Geometry("LINESTRING", srid=4326) if _GEO_AVAILABLE else JSONB,
        nullable=True,
    )
    attributes = Column(JSONB, nullable=False, default=dict)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_track_entity_start", "entity_id", "segment_start"),
    )


# ── source_metadata ───────────────────────────────────────────────────────────


class SourceMetadata(Base):
    """Source health and freshness tracking per connector (P0-5.4).

    Rows are upserted by the connector after each poll cycle.
    """
    __tablename__ = "source_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(128), nullable=False, unique=True, index=True, comment="Connector identifier, e.g. connector.cdse.stac")
    display_name = Column(String(255), nullable=True)
    source_type = Column(String(64), nullable=True)
    last_successful_poll = Column(DateTime(timezone=True), nullable=True)
    last_attempted_poll = Column(DateTime(timezone=True), nullable=True)
    median_delay_seconds = Column(Float, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    consecutive_errors = Column(Integer, nullable=False, default=0)
    total_events_ingested = Column(BigInteger, nullable=False, default=0)
    is_enabled = Column(Boolean, nullable=False, default=True)
    circuit_state = Column(String(16), nullable=False, default="closed", comment="closed|open|half_open")
    config_snapshot = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


# ── analyst_annotations ───────────────────────────────────────────────────────


class AnalystAnnotation(Base):
    """Analyst verdict and notes on a change detection candidate.

    Links a CanonicalEvent (change_detection type) to an AOI and records
    the analyst's review decision (confirmed/dismissed/uncertain).
    """
    __tablename__ = "analyst_annotations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(128), nullable=False, index=True, comment="Points to canonical_events.event_id")
    aoi_id = Column(String(36), ForeignKey("aois.id", ondelete="SET NULL"), nullable=True, index=True)
    analyst_id = Column(String(128), nullable=True, comment="User ID or username")
    review_status = Column(String(32), nullable=False, default="pending", index=True, comment="pending|confirmed|dismissed|uncertain")
    confidence_override = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    evidence = Column(JSONB, nullable=False, default=dict, comment="Links to imagery, events, PDFs")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    aoi = relationship("AOI", back_populates="annotations")

    __table_args__ = (
        Index("ix_annotations_status_aoi", "review_status", "aoi_id"),
    )

