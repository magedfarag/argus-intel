"""Initial PostGIS schema — aois, canonical_events, track_segments, source_metadata, analyst_annotations.

Revision ID: 0001
Revises:
Create Date: 2026-04-03

This migration:
  1. Enables the PostGIS extension (idempotent)
  2. Creates all five core tables with composite indexes (P0-4.2)
  3. Adds a GiST spatial index on geometry columns

To apply:  alembic upgrade head
To revert:  alembic downgrade base
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Use string literals for geometry columns so the migration works both with
# and without GeoAlchemy2 installed in the migration environment.
GEOM_TYPE = sa.Text  # placeholder; overridden in actual column definition


def upgrade() -> None:
    # 1. PostGIS extension (requires superuser; skip if already present)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 2. aois table
    op.create_table(
        "aois",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "geometry",
            sa.Text,
            sa.CheckConstraint("geometry IS NOT NULL"),
            nullable=False,
            comment="PostGIS geometry SRID=4326 stored as WKB/GeoJSON via GeoAlchemy2",
        ),
        sa.Column("tags", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("metadata", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_aois_name", "aois", ["name"])
    op.create_index("ix_aois_deleted_created", "aois", ["deleted", "created_at"])

    # 3. canonical_events table
    op.create_table(
        "canonical_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(128), nullable=False, unique=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(256), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geometry", sa.Text, nullable=True),
        sa.Column("centroid", sa.Text, nullable=True),
        sa.Column("altitude_m", sa.Float, nullable=True),
        sa.Column("attributes", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("normalization", JSONB, nullable=True),
        sa.Column("provenance", JSONB, nullable=True),
        sa.Column("license", JSONB, nullable=True),
        sa.Column("correlation_keys", JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("quality_flags", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("tags", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("primary_aoi_id", sa.String(36), sa.ForeignKey("aois.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_events_event_id", "canonical_events", ["event_id"])
    op.create_index("ix_events_source", "canonical_events", ["source"])
    op.create_index("ix_events_entity_type", "canonical_events", ["entity_type"])
    op.create_index("ix_events_event_type", "canonical_events", ["event_type"])
    op.create_index("ix_events_event_time", "canonical_events", ["event_time"])
    op.create_index("ix_events_ingested_at", "canonical_events", ["ingested_at"])
    op.create_index("ix_events_aoi_time", "canonical_events", ["primary_aoi_id", "event_time"])
    # Composite index (P0-4.2): event_time + source + entity_type
    op.create_index("ix_events_time_source_entity", "canonical_events", ["event_time", "source", "entity_type"])
    # Spatial indexes on geometry/centroid — requires PostGIS (GiST operator class)
    op.execute("""
        ALTER TABLE canonical_events
            ALTER COLUMN geometry TYPE geometry(Geometry, 4326)
            USING ST_SetSRID(ST_GeomFromGeoJSON(geometry), 4326)
    """)
    op.execute("""
        ALTER TABLE canonical_events
            ALTER COLUMN centroid TYPE geometry(Point, 4326)
            USING ST_SetSRID(ST_GeomFromGeoJSON(centroid), 4326)
    """)
    op.execute("CREATE INDEX ix_events_geometry_gist ON canonical_events USING GIST (geometry)")
    op.execute("CREATE INDEX ix_events_centroid_gist ON canonical_events USING GIST (centroid)")

    # Apply geometry to aois table as well
    op.execute("""
        ALTER TABLE aois
            ALTER COLUMN geometry TYPE geometry(Geometry, 4326)
            USING ST_SetSRID(ST_GeomFromGeoJSON(geometry), 4326)
    """)
    op.execute("CREATE INDEX ix_aois_geometry_gist ON aois USING GIST (geometry)")

    # 4. track_segments table
    op.create_table(
        "track_segments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(256), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("segment_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("segment_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("distance_km", sa.Float, nullable=True),
        sa.Column("avg_speed_kn", sa.Float, nullable=True),
        sa.Column("track_geom", sa.Text, nullable=True),
        sa.Column("attributes", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_track_entity_start", "track_segments", ["entity_id", "segment_start"])
    op.create_index("ix_track_entity_type", "track_segments", ["entity_type"])
    op.execute("""
        ALTER TABLE track_segments
            ALTER COLUMN track_geom TYPE geometry(LineString, 4326)
            USING ST_SetSRID(ST_GeomFromGeoJSON(track_geom), 4326)
    """)
    op.execute("CREATE INDEX ix_track_geom_gist ON track_segments USING GIST (track_geom)")

    # 5. source_metadata table
    op.create_table(
        "source_metadata",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("last_successful_poll", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_poll", sa.DateTime(timezone=True), nullable=True),
        sa.Column("median_delay_seconds", sa.Float, nullable=True),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consecutive_errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_events_ingested", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("circuit_state", sa.String(16), nullable=False, server_default="'closed'"),
        sa.Column("config_snapshot", JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_source_metadata_source_id", "source_metadata", ["source_id"])

    # 6. analyst_annotations table
    op.create_table(
        "analyst_annotations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("aoi_id", sa.String(36), sa.ForeignKey("aois.id", ondelete="SET NULL"), nullable=True),
        sa.Column("analyst_id", sa.String(128), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="'pending'"),
        sa.Column("confidence_override", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("evidence", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_annotations_event_id", "analyst_annotations", ["event_id"])
    op.create_index("ix_annotations_aoi_id", "analyst_annotations", ["aoi_id"])
    op.create_index("ix_annotations_status_aoi", "analyst_annotations", ["review_status", "aoi_id"])


def downgrade() -> None:
    op.drop_table("analyst_annotations")
    op.drop_table("source_metadata")
    op.drop_table("track_segments")
    op.drop_table("canonical_events")
    op.drop_table("aois")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    # Do not drop postgis — other schemas may depend on it

