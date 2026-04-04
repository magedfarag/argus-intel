"""Unit tests for the canonical event model and event_id generation.

P0-3.5: ≥20 tests covering required fields, confidence range, UTC enforcement,
determinism, and family attribute models.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.models.canonical_event import (
    AircraftAttributes,
    CanonicalEvent,
    ContextualAttributes,
    CorrelationKeys,
    EntityType,
    EventType,
    ImageryAttributes,
    LicenseRecord,
    NormalizationRecord,
    PermitAttributes,
    ProvenanceRecord,
    ShipPositionAttributes,
    SourceType,
    make_event_id,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _minimal_event(**overrides) -> CanonicalEvent:
    """Return a valid minimal CanonicalEvent, optionally patched by overrides."""
    base = dict(
        event_id="evt_test_abc123",
        source="test-source",
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        event_type=EventType.IMAGERY_ACQUISITION,
        event_time=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        centroid={"type": "Point", "coordinates": [0.5, 0.5]},
        attributes={},
        normalization=NormalizationRecord(normalized_by="test-connector"),
        provenance=ProvenanceRecord(raw_source_ref="s3://bucket/raw/test.json"),
        ingested_at=datetime(2026, 4, 1, 10, 5, 0, tzinfo=timezone.utc),
        license=LicenseRecord(),
    )
    base.update(overrides)
    return CanonicalEvent(**base)


# ── Identity field tests ──────────────────────────────────────────────────────

class TestRequiredFields:
    def test_valid_minimal_event_creates_without_error(self):
        event = _minimal_event()
        assert event.event_id == "evt_test_abc123"

    def test_missing_event_id_raises(self):
        with pytest.raises(ValidationError):
            _minimal_event(event_id=None)

    def test_missing_source_raises(self):
        with pytest.raises((ValidationError, TypeError)):
            CanonicalEvent(
                source_type=SourceType.IMAGERY_CATALOG,
                entity_type=EntityType.IMAGERY_SCENE,
                event_type=EventType.IMAGERY_ACQUISITION,
                event_time=datetime(2026, 4, 1, tzinfo=timezone.utc),
                geometry={"type": "Polygon", "coordinates": []},
                centroid={"type": "Point", "coordinates": [0, 0]},
                attributes={},
                normalization=NormalizationRecord(normalized_by="x"),
                provenance=ProvenanceRecord(raw_source_ref="s3://x"),
                license=LicenseRecord(),
            )

    def test_event_type_enum_stored_correctly(self):
        event = _minimal_event()
        assert event.event_type == EventType.IMAGERY_ACQUISITION

    def test_source_type_enum(self):
        event = _minimal_event(source_type=SourceType.TELEMETRY)
        assert event.source_type == SourceType.TELEMETRY

    def test_entity_type_enum(self):
        event = _minimal_event(entity_type=EntityType.VESSEL)
        assert event.entity_type == EntityType.VESSEL


# ── UTC enforcement tests ─────────────────────────────────────────────────────

class TestUTCEnforcement:
    def test_z_suffix_string_accepted(self):
        event = _minimal_event(event_time="2026-04-01T10:00:00Z")
        assert event.event_time.tzinfo is not None

    def test_plus00_string_accepted(self):
        event = _minimal_event(event_time="2026-04-01T10:00:00+00:00")
        assert event.event_time.tzinfo is not None

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_event(event_time=datetime(2026, 4, 1, 10, 0, 0))  # no tz

    def test_none_optional_time_fields_allowed(self):
        event = _minimal_event(time_start=None, time_end=None)
        assert event.time_start is None
        assert event.time_end is None

    def test_time_interval_order_enforced(self):
        with pytest.raises(ValidationError):
            _minimal_event(
                time_start=datetime(2026, 4, 2, tzinfo=timezone.utc),
                time_end=datetime(2026, 4, 1, tzinfo=timezone.utc),
            )

    def test_valid_time_interval_accepted(self):
        event = _minimal_event(
            time_start=datetime(2026, 4, 1, tzinfo=timezone.utc),
            time_end=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )
        assert event.time_start < event.time_end


# ── Confidence range tests ────────────────────────────────────────────────────

class TestConfidenceRange:
    def test_zero_confidence_accepted(self):
        event = _minimal_event(confidence=0.0)
        assert event.confidence == 0.0

    def test_one_confidence_accepted(self):
        event = _minimal_event(confidence=1.0)
        assert event.confidence == 1.0

    def test_mid_confidence_accepted(self):
        event = _minimal_event(confidence=0.75)
        assert event.confidence == 0.75

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_event(confidence=1.1)

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_event(confidence=-0.1)

    def test_none_confidence_accepted(self):
        event = _minimal_event(confidence=None)
        assert event.confidence is None


# ── Geometry validation tests ─────────────────────────────────────────────────

class TestGeometryValidation:
    def test_missing_type_in_geometry_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_event(geometry={"coordinates": []})

    def test_centroid_non_point_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_event(centroid={"type": "Polygon", "coordinates": []})

    def test_valid_multipolygon_geometry(self):
        event = _minimal_event(
            geometry={
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            }
        )
        assert event.geometry["type"] == "MultiPolygon"


# ── Sub-model tests ───────────────────────────────────────────────────────────

class TestSubModels:
    def test_normalization_record_defaults(self):
        n = NormalizationRecord(normalized_by="connector.cdse.stac")
        assert n.schema_version == "1.0.0"
        assert n.normalization_warnings == []
        assert n.dedupe_key is None

    def test_correlation_keys_defaults(self):
        ck = CorrelationKeys()
        assert ck.aoi_ids == []
        assert ck.mmsi is None

    def test_license_record_defaults(self):
        lr = LicenseRecord()
        assert lr.access_tier == "public"
        assert lr.attribution_required is True

    def test_imagery_attributes_cloud_cover_bounds(self):
        with pytest.raises(ValidationError):
            ImageryAttributes(cloud_cover_pct=101.0)

    def test_ship_position_speed_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            ShipPositionAttributes(speed_kn=-1.0)


# ── make_event_id utility tests ───────────────────────────────────────────────

class TestMakeEventId:
    def test_deterministic_from_same_inputs(self):
        id1 = make_event_id("copernicus-cdse", "SCENE_001", "2026-04-01T10:00:00Z")
        id2 = make_event_id("copernicus-cdse", "SCENE_001", "2026-04-01T10:00:00Z")
        assert id1 == id2

    def test_different_entities_produce_different_ids(self):
        id1 = make_event_id("source-a", "scene-1", "2026-04-01T10:00:00Z")
        id2 = make_event_id("source-a", "scene-2", "2026-04-01T10:00:00Z")
        assert id1 != id2

    def test_different_times_produce_different_ids(self):
        id1 = make_event_id("source-a", "scene-1", "2026-04-01T10:00:00Z")
        id2 = make_event_id("source-a", "scene-1", "2026-04-01T11:00:00Z")
        assert id1 != id2

    def test_datetime_and_string_produce_same_id(self):
        dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        id_dt = make_event_id("src", "entity", dt)
        id_str = make_event_id("src", "entity", "2026-04-01T10:00:00+00:00")
        assert id_dt == id_str

    def test_id_format_starts_with_evt_prefix(self):
        event_id = make_event_id("copernicus-cdse", "S2A_001", "2026-04-01T00:00:00Z")
        assert event_id.startswith("evt_copernicus-cdse_")

    def test_id_length_is_stable(self):
        id1 = make_event_id("s", "e", "2026-01-01T00:00:00Z")
        id2 = make_event_id("longer-source", "longer-entity-id", "2026-12-31T23:59:59Z")
        # prefix varies but digest portion is always 12 hex chars
        assert id1.split("_")[-1].__len__() == 12
        assert id2.split("_")[-1].__len__() == 12
