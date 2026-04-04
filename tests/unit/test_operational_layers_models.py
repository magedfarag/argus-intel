"""Unit tests for Phase 2 operational-layer Pydantic models.

Covers:
- All 7 new models: SatelliteOrbit, SatellitePass, AirspaceRestriction,
  NotamEvent, GpsJammingEvent, StrikeEvent, EvidenceLink
- UTC-aware datetime enforcement
- SatellitePass AOS < LOS validation
- Confidence range bounds on GpsJammingEvent and StrikeEvent
- New EventType enum values
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from src.models.operational_layers import (
    AirspaceRestriction,
    EvidenceLink,
    GpsJammingEvent,
    NotamEvent,
    SatelliteOrbit,
    SatellitePass,
    StrikeEvent,
)
from src.models.canonical_event import EventType

# ── Shared UTC timestamps ─────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
_PAST = _NOW - timedelta(hours=2)
_FUTURE = _NOW + timedelta(hours=2)

_GEO_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-77.5, 38.5], [-76.8, 38.5], [-76.8, 39.1], [-77.5, 39.1], [-77.5, 38.5]]],
}


# ──────────────────────────────────────────────────────────────────────────────
# EventType enum — new Phase 2 values
# ──────────────────────────────────────────────────────────────────────────────


class TestEventTypeEnumNewValues:
    def test_satellite_pass_value(self):
        assert EventType.SATELLITE_PASS == "satellite_pass"

    def test_satellite_orbit_value(self):
        assert EventType.SATELLITE_ORBIT == "satellite_orbit"

    def test_airspace_restriction_value(self):
        assert EventType.AIRSPACE_RESTRICTION == "airspace_restriction"

    def test_notam_event_value(self):
        assert EventType.NOTAM_EVENT == "notam_event"

    def test_gps_jamming_event_value(self):
        assert EventType.GPS_JAMMING_EVENT == "gps_jamming_event"

    def test_strike_event_value(self):
        assert EventType.STRIKE_EVENT == "strike_event"

    def test_all_six_new_values_importable(self):
        new_values = [
            EventType.SATELLITE_PASS,
            EventType.SATELLITE_ORBIT,
            EventType.AIRSPACE_RESTRICTION,
            EventType.NOTAM_EVENT,
            EventType.GPS_JAMMING_EVENT,
            EventType.STRIKE_EVENT,
        ]
        assert len(new_values) == 6


# ──────────────────────────────────────────────────────────────────────────────
# SatelliteOrbit
# ──────────────────────────────────────────────────────────────────────────────


class TestSatelliteOrbit:
    def test_minimal_valid_instantiation(self):
        orbit = SatelliteOrbit(
            satellite_id="SENTINEL-2A",
            source="space-track.org",
        )
        assert orbit.satellite_id == "SENTINEL-2A"
        assert orbit.source == "space-track.org"

    def test_full_instantiation_with_optional_fields(self):
        orbit = SatelliteOrbit(
            satellite_id="ISS-(ZARYA)",
            norad_id=25544,
            tle_line1="1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994",
            tle_line2="2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123",
            orbital_period_minutes=92.5,
            inclination_deg=51.6,
            altitude_km=410.0,
            source="celestrak",
            loaded_at=_NOW,
        )
        assert orbit.norad_id == 25544
        assert orbit.orbital_period_minutes == 92.5
        assert orbit.inclination_deg == 51.6
        assert orbit.altitude_km == 410.0

    def test_loaded_at_defaults_to_utc_aware(self):
        orbit = SatelliteOrbit(satellite_id="TEST-SAT", source="test")
        assert orbit.loaded_at.tzinfo is not None

    def test_naive_loaded_at_raises(self):
        naive = datetime(2026, 4, 4, 12, 0, 0)
        with pytest.raises(ValidationError):
            SatelliteOrbit(satellite_id="TEST-SAT", source="test", loaded_at=naive)

    def test_iso_string_loaded_at_accepted(self):
        orbit = SatelliteOrbit(
            satellite_id="TEST-SAT",
            source="test",
            loaded_at="2026-04-04T12:00:00+00:00",
        )
        assert orbit.loaded_at.tzinfo is not None

    def test_inclination_deg_boundary_zero(self):
        orbit = SatelliteOrbit(satellite_id="S", source="s", inclination_deg=0.0)
        assert orbit.inclination_deg == 0.0

    def test_inclination_deg_boundary_180(self):
        orbit = SatelliteOrbit(satellite_id="S", source="s", inclination_deg=180.0)
        assert orbit.inclination_deg == 180.0

    def test_altitude_km_must_be_positive(self):
        with pytest.raises(ValidationError):
            SatelliteOrbit(satellite_id="S", source="s", altitude_km=0.0)


# ──────────────────────────────────────────────────────────────────────────────
# SatellitePass
# ──────────────────────────────────────────────────────────────────────────────


class TestSatellitePass:
    def _make_pass(self, **kwargs) -> SatellitePass:
        base = dict(
            satellite_id="ISS-(ZARYA)",
            aos=_PAST,
            los=_FUTURE,
            source="tle-stub",
        )
        base.update(kwargs)
        return SatellitePass(**base)

    def test_valid_pass_instantiates(self):
        sp = self._make_pass()
        assert sp.satellite_id == "ISS-(ZARYA)"
        assert sp.aos < sp.los

    def test_aos_ge_los_raises_value_error(self):
        with pytest.raises((ValidationError, ValueError)):
            SatellitePass(
                satellite_id="X",
                aos=_FUTURE,
                los=_PAST,
                source="test",
            )

    def test_aos_equals_los_raises(self):
        same = _NOW
        with pytest.raises((ValidationError, ValueError)):
            SatellitePass(
                satellite_id="X",
                aos=same,
                los=same,
                source="test",
            )

    def test_naive_aos_raises(self):
        naive = datetime(2026, 4, 4, 10, 0, 0)
        with pytest.raises(ValidationError):
            SatellitePass(
                satellite_id="X",
                aos=naive,
                los=_FUTURE,
                source="test",
            )

    def test_naive_los_raises(self):
        naive = datetime(2026, 4, 4, 14, 0, 0)
        with pytest.raises(ValidationError):
            SatellitePass(
                satellite_id="X",
                aos=_PAST,
                los=naive,
                source="test",
            )

    def test_confidence_default_is_one(self):
        sp = self._make_pass()
        assert sp.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            self._make_pass(confidence=-0.01)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            self._make_pass(confidence=1.01)

    def test_confidence_boundary_zero(self):
        sp = self._make_pass(confidence=0.0)
        assert sp.confidence == 0.0

    def test_confidence_boundary_one(self):
        sp = self._make_pass(confidence=1.0)
        assert sp.confidence == 1.0

    def test_footprint_geojson_accepted_when_valid(self):
        sp = self._make_pass(footprint_geojson=_GEO_POLYGON)
        assert sp.footprint_geojson is not None

    def test_footprint_geojson_rejected_without_type(self):
        with pytest.raises(ValidationError):
            self._make_pass(footprint_geojson={"coordinates": [[[0, 0]]]})

    def test_footprint_geojson_none_accepted(self):
        sp = self._make_pass(footprint_geojson=None)
        assert sp.footprint_geojson is None


# ──────────────────────────────────────────────────────────────────────────────
# AirspaceRestriction
# ──────────────────────────────────────────────────────────────────────────────


class TestAirspaceRestriction:
    def test_valid_instantiation(self):
        r = AirspaceRestriction(
            restriction_id="TFR-TEST-001",
            name="TEST TFR",
            restriction_type="TFR",
            geometry_geojson=_GEO_POLYGON,
            valid_from=_PAST,
            source="faa-stub",
        )
        assert r.restriction_id == "TFR-TEST-001"
        assert r.restriction_type == "TFR"

    def test_valid_to_none_accepted(self):
        r = AirspaceRestriction(
            restriction_id="R-001",
            name="Permanent",
            restriction_type="NFZ",
            geometry_geojson=_GEO_POLYGON,
            valid_from=_PAST,
            valid_to=None,
            source="test",
        )
        assert r.valid_to is None

    def test_naive_valid_from_raises(self):
        naive = datetime(2026, 4, 1, 0, 0, 0)
        with pytest.raises(ValidationError):
            AirspaceRestriction(
                restriction_id="R-001",
                name="Test",
                restriction_type="TFR",
                geometry_geojson=_GEO_POLYGON,
                valid_from=naive,
                source="test",
            )

    def test_geojson_without_type_raises(self):
        with pytest.raises(ValidationError):
            AirspaceRestriction(
                restriction_id="R-001",
                name="Test",
                restriction_type="TFR",
                geometry_geojson={"coordinates": [[]]},
                valid_from=_PAST,
                source="test",
            )

    def test_is_active_defaults_true(self):
        r = AirspaceRestriction(
            restriction_id="R-002",
            name="Active",
            restriction_type="MOA",
            geometry_geojson=_GEO_POLYGON,
            valid_from=_PAST,
            source="test",
        )
        assert r.is_active is True


# ──────────────────────────────────────────────────────────────────────────────
# NotamEvent
# ──────────────────────────────────────────────────────────────────────────────


class TestNotamEvent:
    def test_valid_instantiation(self):
        n = NotamEvent(
            notam_id="notam-test-001",
            notam_number="A0001/26",
            subject="Test NOTAM",
            condition="RWY CLSD",
            location_icao="KDCA",
            effective_from=_PAST,
            source="faa-stub",
        )
        assert n.notam_id == "notam-test-001"
        assert n.location_icao == "KDCA"

    def test_effective_to_none_accepted(self):
        n = NotamEvent(
            notam_id="notam-002",
            notam_number="A0002/26",
            subject="Open-ended NOTAM",
            condition="PERM",
            location_icao="KJFK",
            effective_from=_PAST,
            effective_to=None,
            source="faa-stub",
        )
        assert n.effective_to is None

    def test_naive_effective_from_raises(self):
        with pytest.raises(ValidationError):
            NotamEvent(
                notam_id="n-001",
                notam_number="A0003/26",
                subject="Test",
                condition="TEST",
                location_icao="KLAX",
                effective_from=datetime(2026, 4, 1),
                source="test",
            )

    def test_geometry_geojson_optional(self):
        n = NotamEvent(
            notam_id="n-002",
            notam_number="A0004/26",
            subject="No geometry",
            condition="NO GEO",
            location_icao="KORD",
            effective_from=_PAST,
            geometry_geojson=None,
            source="test",
        )
        assert n.geometry_geojson is None


# ──────────────────────────────────────────────────────────────────────────────
# GpsJammingEvent
# ──────────────────────────────────────────────────────────────────────────────


class TestGpsJammingEvent:
    def _make_jamming(self, **kwargs) -> GpsJammingEvent:
        base = dict(
            jamming_id="jam-test-001",
            detected_at=_PAST,
            location_lon=33.60,
            location_lat=35.10,
            radius_km=100.0,
            jamming_type="spoofing",
            detection_method="derived",
            confidence=0.85,
            source="gnss-stub",
            provenance="gps-jammer-tracker-stub",
        )
        base.update(kwargs)
        return GpsJammingEvent(**base)

    def test_valid_instantiation(self):
        ev = self._make_jamming()
        assert ev.jamming_id == "jam-test-001"
        assert ev.confidence == 0.85

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            self._make_jamming(confidence=-0.01)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            self._make_jamming(confidence=1.01)

    def test_confidence_boundary_zero(self):
        ev = self._make_jamming(confidence=0.0)
        assert ev.confidence == 0.0

    def test_confidence_boundary_one(self):
        ev = self._make_jamming(confidence=1.0)
        assert ev.confidence == 1.0

    def test_naive_detected_at_raises(self):
        with pytest.raises(ValidationError):
            self._make_jamming(detected_at=datetime(2026, 4, 1, 12, 0, 0))

    def test_invalid_detection_method_raises(self):
        with pytest.raises(ValidationError):
            self._make_jamming(detection_method="unknown-method")

    def test_valid_detection_methods(self):
        for method in ("derived", "reported", "confirmed"):
            ev = self._make_jamming(detection_method=method)
            assert ev.detection_method == method

    def test_affected_area_geojson_accepted_when_valid(self):
        ev = self._make_jamming(affected_area_geojson=_GEO_POLYGON)
        assert ev.affected_area_geojson is not None

    def test_affected_area_geojson_rejected_without_coordinates(self):
        with pytest.raises(ValidationError):
            self._make_jamming(affected_area_geojson={"type": "Polygon"})


# ──────────────────────────────────────────────────────────────────────────────
# StrikeEvent
# ──────────────────────────────────────────────────────────────────────────────


class TestStrikeEvent:
    def _make_strike(self, **kwargs) -> StrikeEvent:
        base = dict(
            strike_id="strike-test-001",
            occurred_at=_PAST,
            location_lon=37.8,
            location_lat=47.9,
            strike_type="airstrike",
            confidence=0.75,
            source="acled-stub",
            provenance="acled-stub://strike-test-001",
        )
        base.update(kwargs)
        return StrikeEvent(**base)

    def test_valid_instantiation(self):
        ev = self._make_strike()
        assert ev.strike_id == "strike-test-001"
        assert ev.confidence == 0.75

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            self._make_strike(confidence=-0.01)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            self._make_strike(confidence=1.01)

    def test_confidence_boundary_values(self):
        ev0 = self._make_strike(confidence=0.0)
        ev1 = self._make_strike(confidence=1.0)
        assert ev0.confidence == 0.0
        assert ev1.confidence == 1.0

    def test_naive_occurred_at_raises(self):
        with pytest.raises(ValidationError):
            self._make_strike(occurred_at=datetime(2026, 4, 1, 8, 0, 0))

    def test_evidence_refs_defaults_empty(self):
        ev = self._make_strike()
        assert ev.evidence_refs == []

    def test_corroboration_count_defaults_zero(self):
        ev = self._make_strike()
        assert ev.corroboration_count == 0

    def test_corroboration_count_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            self._make_strike(corroboration_count=-1)

    def test_location_lon_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            self._make_strike(location_lon=190.0)

    def test_location_lat_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            self._make_strike(location_lat=-95.0)

    def test_location_geojson_rejected_without_coordinates(self):
        with pytest.raises(ValidationError):
            self._make_strike(location_geojson={"type": "Point"})


# ──────────────────────────────────────────────────────────────────────────────
# EvidenceLink
# ──────────────────────────────────────────────────────────────────────────────


class TestEvidenceLink:
    def test_valid_instantiation(self):
        link = EvidenceLink(
            evidence_id="ev-abc123",
            event_id="strike-test-001",
            evidence_type="imagery",
        )
        assert link.evidence_id == "ev-abc123"
        assert link.event_id == "strike-test-001"
        assert link.evidence_type == "imagery"

    def test_added_at_defaults_to_utc_aware(self):
        link = EvidenceLink(
            evidence_id="ev-001",
            event_id="evt-001",
            evidence_type="report",
        )
        assert link.added_at.tzinfo is not None

    def test_confidence_defaults_to_one(self):
        link = EvidenceLink(
            evidence_id="ev-001",
            event_id="evt-001",
            evidence_type="ais_record",
        )
        assert link.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            EvidenceLink(
                evidence_id="ev-001",
                event_id="evt-001",
                evidence_type="imagery",
                confidence=-0.1,
            )

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            EvidenceLink(
                evidence_id="ev-001",
                event_id="evt-001",
                evidence_type="imagery",
                confidence=1.1,
            )

    def test_optional_fields_none(self):
        link = EvidenceLink(
            evidence_id="ev-002",
            event_id="evt-002",
            evidence_type="social_media",
            url=None,
            description=None,
        )
        assert link.url is None
        assert link.description is None

    def test_url_and_description_accepted(self):
        link = EvidenceLink(
            evidence_id="ev-003",
            event_id="evt-003",
            evidence_type="imagery",
            url="https://example.com/image.jpg",
            description="Satellite imagery of impact site",
        )
        assert link.url == "https://example.com/image.jpg"
        assert "Satellite" in link.description
