"""Unit tests for Phase 2 operational-layer connector stubs.

Covers:
- OrbitConnector: ingest_orbits, compute_passes
- AirspaceConnector: fetch_restrictions, fetch_notams, is_active
- JammingConnector: detect_jamming_events (count, confidence range, determinism)
- StrikeConnector: fetch_strikes, add_evidence (corroboration increment, idempotency)
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from src.connectors.orbit_connector import OrbitConnector
from src.connectors.airspace_connector import AirspaceConnector
from src.connectors.jamming_connector import JammingConnector
from src.connectors.strike_connector import StrikeConnector
from src.models.operational_layers import (
    AirspaceRestriction,
    EvidenceLink,
    GpsJammingEvent,
    SatelliteOrbit,
    SatellitePass,
    StrikeEvent,
)

# ── Shared time window ────────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
_WINDOW_START = _NOW - timedelta(days=30)
_WINDOW_END = _NOW

_ISS_TLE = """\
ISS (ZARYA)
1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994
2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123
"""

_MULTI_TLE = """\
ISS (ZARYA)
1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994
2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123
SENTINEL-2A
1 40697U 15028A   26094.50000000  .00000050  00000-0  17800-4 0  9991
2 40697  98.5683  62.2784 0001123  84.5271 275.6031 14.30820001562811
"""


# ──────────────────────────────────────────────────────────────────────────────
# OrbitConnector
# ──────────────────────────────────────────────────────────────────────────────


class TestOrbitConnector:
    @pytest.fixture(scope="class")
    def connector(self) -> OrbitConnector:
        c = OrbitConnector()
        c.connect()
        return c

    def test_ingest_orbits_returns_satellite_orbit_objects(self, connector):
        orbits = connector.ingest_orbits(_ISS_TLE)
        assert len(orbits) >= 1
        assert all(isinstance(o, SatelliteOrbit) for o in orbits)

    def test_ingest_orbits_parses_satellite_id(self, connector):
        orbits = connector.ingest_orbits(_ISS_TLE)
        ids = [o.satellite_id for o in orbits]
        assert "ISS-(ZARYA)" in ids

    def test_ingest_multiple_tle_triplets(self, connector):
        c2 = OrbitConnector()
        c2.connect()
        orbits = c2.ingest_orbits(_MULTI_TLE)
        assert len(orbits) == 2

    def test_ingest_orbits_sets_utc_aware_loaded_at(self, connector):
        orbits = connector.ingest_orbits(_ISS_TLE)
        for orb in orbits:
            assert orb.loaded_at.tzinfo is not None

    def test_ingest_orbits_parses_norad_id(self, connector):
        c3 = OrbitConnector()
        c3.connect()
        orbits = c3.ingest_orbits(_ISS_TLE)
        assert orbits[0].norad_id == 25544

    def test_ingest_orbits_parses_inclination(self, connector):
        c4 = OrbitConnector()
        c4.connect()
        orbits = c4.ingest_orbits(_ISS_TLE)
        assert orbits[0].inclination_deg is not None
        assert 50.0 < orbits[0].inclination_deg < 53.0

    def test_ingest_orbits_computes_orbital_period(self, connector):
        c5 = OrbitConnector()
        c5.connect()
        orbits = c5.ingest_orbits(_ISS_TLE)
        assert orbits[0].orbital_period_minutes is not None
        assert 88.0 < orbits[0].orbital_period_minutes < 100.0

    def test_compute_passes_returns_satellite_pass_objects(self, connector):
        connector.ingest_orbits(_ISS_TLE)
        passes = connector.compute_passes("ISS-(ZARYA)", lon=0.0, lat=51.5, horizon_hours=24)
        assert isinstance(passes, list)
        assert len(passes) >= 1
        assert all(isinstance(p, SatellitePass) for p in passes)

    def test_compute_passes_all_utc_aware(self, connector):
        connector.ingest_orbits(_ISS_TLE)
        passes = connector.compute_passes("ISS-(ZARYA)", lon=0.0, lat=51.5, horizon_hours=24)
        for p in passes:
            assert p.aos.tzinfo is not None
            assert p.los.tzinfo is not None

    def test_compute_passes_aos_before_los(self, connector):
        connector.ingest_orbits(_ISS_TLE)
        passes = connector.compute_passes("ISS-(ZARYA)", lon=0.0, lat=51.5, horizon_hours=24)
        for p in passes:
            assert p.aos < p.los

    def test_compute_passes_unknown_satellite_raises(self, connector):
        with pytest.raises((KeyError, ValueError, AttributeError)):
            connector.compute_passes("UNKNOWN-SAT-XXXXXX", lon=0.0, lat=51.5, horizon_hours=24)

    def test_ingested_orbits_stored_in_connector(self, connector):
        c6 = OrbitConnector()
        c6.connect()
        c6.ingest_orbits(_MULTI_TLE)
        assert "ISS-(ZARYA)" in c6._orbits
        assert "SENTINEL-2A" in c6._orbits

    def test_blank_lines_in_tle_ignored(self, connector):
        tle_with_blanks = "\n" + _ISS_TLE + "\n\n"
        c7 = OrbitConnector()
        c7.connect()
        orbits = c7.ingest_orbits(tle_with_blanks)
        assert len(orbits) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# AirspaceConnector
# ──────────────────────────────────────────────────────────────────────────────


class TestAirspaceConnector:
    @pytest.fixture(scope="class")
    def connector(self) -> AirspaceConnector:
        c = AirspaceConnector()
        c.connect()
        return c

    def test_fetch_restrictions_returns_list(self, connector):
        results = connector.fetch_restrictions()
        assert isinstance(results, list)
        assert len(results) >= 3

    def test_fetch_restrictions_all_are_airspace_restriction(self, connector):
        results = connector.fetch_restrictions()
        assert all(isinstance(r, AirspaceRestriction) for r in results)

    def test_fetch_restrictions_contains_expired_entry(self, connector):
        results = connector.fetch_restrictions()
        expired = [r for r in results if not r.is_active]
        assert len(expired) >= 1

    def test_fetch_restrictions_contains_active_entries(self, connector):
        results = connector.fetch_restrictions()
        active = [r for r in results if r.is_active]
        assert len(active) >= 3

    def test_fetch_notams_returns_list(self, connector):
        results = connector.fetch_notams()
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_fetch_notams_filter_by_icao(self, connector):
        kdca_notams = connector.fetch_notams("KDCA")
        assert len(kdca_notams) >= 1
        assert all(n.location_icao == "KDCA" for n in kdca_notams)

    def test_fetch_notams_icao_filter_case_insensitive(self, connector):
        upper = connector.fetch_notams("KDCA")
        lower = connector.fetch_notams("kdca")
        assert len(upper) == len(lower)

    def test_fetch_notams_unknown_icao_returns_empty(self, connector):
        results = connector.fetch_notams("ZZZZ")
        assert results == []

    def test_is_active_returns_true_for_current_restriction(self, connector):
        now = datetime.now(timezone.utc)
        restriction = AirspaceRestriction(
            restriction_id="active-test",
            name="Active Test",
            restriction_type="TFR",
            geometry_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            valid_from=now - timedelta(hours=1),
            valid_to=now + timedelta(hours=1),
            is_active=True,
            source="test",
        )
        assert AirspaceConnector.is_active(restriction) is True

    def test_is_active_returns_false_for_expired_restriction(self, connector):
        now = datetime.now(timezone.utc)
        restriction = AirspaceRestriction(
            restriction_id="expired-test",
            name="Expired Test",
            restriction_type="TFR",
            geometry_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            valid_from=now - timedelta(days=5),
            valid_to=now - timedelta(days=1),
            is_active=False,
            source="test",
        )
        assert AirspaceConnector.is_active(restriction) is False

    def test_is_active_returns_true_for_indefinite_restriction(self, connector):
        now = datetime.now(timezone.utc)
        restriction = AirspaceRestriction(
            restriction_id="perm-test",
            name="Permanent Test",
            restriction_type="NFZ",
            geometry_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            valid_from=now - timedelta(days=365),
            valid_to=None,
            is_active=True,
            source="test",
        )
        assert AirspaceConnector.is_active(restriction) is True

    def test_all_datetimes_utc_aware(self, connector):
        for r in connector.fetch_restrictions():
            assert r.valid_from.tzinfo is not None
            if r.valid_to is not None:
                assert r.valid_to.tzinfo is not None
        for n in connector.fetch_notams():
            assert n.effective_from.tzinfo is not None


# ──────────────────────────────────────────────────────────────────────────────
# JammingConnector
# ──────────────────────────────────────────────────────────────────────────────


class TestJammingConnector:
    @pytest.fixture(scope="class")
    def connector(self) -> JammingConnector:
        return JammingConnector()

    def test_detect_jamming_events_returns_list(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        assert isinstance(events, list)

    def test_detect_jamming_events_count_in_range(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        assert 3 <= len(events) <= 5

    def test_detect_jamming_events_all_gps_jamming_event(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        assert all(isinstance(e, GpsJammingEvent) for e in events)

    def test_detect_jamming_confidence_in_range(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert 0.0 <= ev.confidence <= 1.0

    def test_detect_jamming_all_utc_aware_datetimes(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert ev.detected_at.tzinfo is not None

    def test_detect_jamming_is_deterministic(self, connector):
        events1 = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        events2 = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        ids1 = [e.jamming_id for e in events1]
        ids2 = [e.jamming_id for e in events2]
        assert ids1 == ids2

    def test_detect_jamming_different_windows_different_results(self, connector):
        events_a = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        earlier_start = _WINDOW_START - timedelta(days=30)
        events_b = connector.detect_jamming_events(earlier_start, _WINDOW_START)
        ids_a = {e.jamming_id for e in events_a}
        ids_b = {e.jamming_id for e in events_b}
        assert ids_a != ids_b

    def test_detect_jamming_detected_at_within_window(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert _WINDOW_START <= ev.detected_at <= _WINDOW_END

    def test_detect_jamming_source_field_set(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert ev.source != ""

    def test_detect_jamming_provenance_field_set(self, connector):
        events = connector.detect_jamming_events(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert ev.provenance != ""


# ──────────────────────────────────────────────────────────────────────────────
# StrikeConnector
# ──────────────────────────────────────────────────────────────────────────────


class TestStrikeConnector:
    @pytest.fixture(scope="class")
    def connector(self) -> StrikeConnector:
        return StrikeConnector()

    def test_fetch_strikes_returns_list(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        assert isinstance(events, list)

    def test_fetch_strikes_count_in_range(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        assert 4 <= len(events) <= 6

    def test_fetch_strikes_all_strike_event(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        assert all(isinstance(e, StrikeEvent) for e in events)

    def test_fetch_strikes_confidence_in_range(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert 0.0 <= ev.confidence <= 1.0

    def test_fetch_strikes_all_utc_aware(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert ev.occurred_at.tzinfo is not None

    def test_fetch_strikes_evidence_refs_non_empty(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        assert any(len(ev.evidence_refs) > 0 for ev in events)

    def test_fetch_strikes_is_deterministic(self, connector):
        events1 = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        events2 = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        ids1 = [e.strike_id for e in events1]
        ids2 = [e.strike_id for e in events2]
        assert ids1 == ids2

    def test_add_evidence_increments_corroboration_count(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        base = events[0]
        link = EvidenceLink(
            evidence_id="ev-test-001",
            event_id=base.strike_id,
            evidence_type="imagery",
        )
        updated = connector.add_evidence(base, [link])
        assert updated.corroboration_count == base.corroboration_count + 1

    def test_add_evidence_adds_evidence_id_to_refs(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        base = events[0]
        link = EvidenceLink(
            evidence_id="ev-test-002",
            event_id=base.strike_id,
            evidence_type="report",
        )
        updated = connector.add_evidence(base, [link])
        assert "ev-test-002" in updated.evidence_refs

    def test_add_evidence_is_idempotent(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        base = events[0]
        link = EvidenceLink(
            evidence_id="ev-idem-001",
            event_id=base.strike_id,
            evidence_type="imagery",
        )
        once = connector.add_evidence(base, [link])
        twice = connector.add_evidence(once, [link])
        assert twice.corroboration_count == once.corroboration_count
        assert twice.evidence_refs.count("ev-idem-001") == 1

    def test_add_evidence_does_not_mutate_original(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        base = events[0]
        original_count = base.corroboration_count
        link = EvidenceLink(
            evidence_id="ev-immut-001",
            event_id=base.strike_id,
            evidence_type="report",
        )
        connector.add_evidence(base, [link])
        assert base.corroboration_count == original_count

    def test_fetch_strikes_provenance_non_empty(self, connector):
        events = connector.fetch_strikes(_WINDOW_START, _WINDOW_END)
        for ev in events:
            assert ev.provenance != ""
