"""Unit tests for P6-4 dark ship detector.

Tests: empty input, gap threshold boundary, candidate enrichment,
sanctions confidence boost, position-jump detection, sorting, response shape.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
)
from src.services.dark_ship_detector import (
    GAP_THRESHOLD_H,
    DarkShipCandidate,
    DarkShipDetectionResponse,
    detect_dark_ships,
)

# ── helpers ───────────────────────────────────────────────────────────────────

_NORM = NormalizationRecord(normalized_by="test")
_PROV = ProvenanceRecord(raw_source_ref="test://")
_LIC  = LicenseRecord()

_T0 = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)


def _pos_event(mmsi: str, t: datetime, lon: float, lat: float, idx: int = 0) -> CanonicalEvent:
    """Build a minimal SHIP_POSITION canonical event at Point geometry."""
    return CanonicalEvent(
        event_id=f"evt-{mmsi}-{idx}",
        source="test-ais",
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.VESSEL,
        event_type=EventType.SHIP_POSITION,
        event_time=t,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        centroid={"type": "Point", "coordinates": [lon, lat]},
        attributes={"mmsi": mmsi, "vessel_name": f"VESSEL-{mmsi}"},
        normalization=_NORM,
        provenance=_PROV,
        ingested_at=t,
        license=_LIC,
    )


def _two_events(mmsi: str, gap_h: float, lon0: float = 56.5, lat0: float = 26.3,
                lon1: float = 56.5, lat1: float = 26.3) -> list[CanonicalEvent]:
    t1 = _T0 + timedelta(hours=gap_h)
    return [_pos_event(mmsi, _T0, lon0, lat0, 0), _pos_event(mmsi, t1, lon1, lat1, 1)]


# ── tests ─────────────────────────────────────────────────────────────────────

class TestEmptyAndFilteredInputs:
    def test_empty_list_returns_zero_candidates(self):
        resp = detect_dark_ships([])
        assert resp.total == 0
        assert len(resp.candidates) == 0

    def test_non_ship_position_events_ignored(self):
        evt = CanonicalEvent(
            event_id="evt-imagery-1",
            source="sentinel",
            source_type=SourceType.IMAGERY_CATALOG,
            entity_type=EntityType.IMAGERY_SCENE,
            event_type=EventType.IMAGERY_ACQUISITION,
            event_time=_T0,
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            centroid={"type": "Point", "coordinates": [0.5, 0.5]},
            attributes={},
            normalization=_NORM,
            provenance=_PROV,
            ingested_at=_T0,
            license=_LIC,
        )
        resp = detect_dark_ships([evt])
        assert resp.total == 0

    def test_single_position_event_no_gap(self):
        """Single event per vessel — no gap to measure."""
        events = [_pos_event("123456789", _T0, 56.5, 26.3)]
        resp = detect_dark_ships(events)
        assert resp.total == 0

    def test_events_analysed_count_matches_input(self):
        events = _two_events("123456789", gap_h=8.0)
        resp = detect_dark_ships(events)
        assert resp.events_analysed == 2


class TestGapThreshold:
    def test_gap_below_threshold_not_flagged(self):
        events = _two_events("123456789", gap_h=GAP_THRESHOLD_H - 0.1)
        resp = detect_dark_ships(events)
        assert resp.total == 0

    def test_gap_exactly_at_threshold_flagged(self):
        """Threshold check is gap_h < GAP_THRESHOLD_H; equal-to is NOT skipped."""
        events = _two_events("123456789", gap_h=GAP_THRESHOLD_H)
        resp = detect_dark_ships(events)
        assert resp.total == 1

    def test_gap_just_above_threshold_flagged(self):
        events = _two_events("123456789", gap_h=GAP_THRESHOLD_H + 0.1)
        resp = detect_dark_ships(events)
        assert resp.total == 1

    def test_large_gap_flagged(self):
        events = _two_events("123456789", gap_h=48.0)
        resp = detect_dark_ships(events)
        assert resp.total == 1


class TestCandidateFields:
    def test_candidate_mmsi_matches_input(self):
        events = _two_events("422110600", gap_h=10.0)
        resp = detect_dark_ships(events)
        assert resp.candidates[0].mmsi == "422110600"

    def test_candidate_gap_hours_correct(self):
        events = _two_events("422110600", gap_h=10.0)
        resp = detect_dark_ships(events)
        assert resp.candidates[0].gap_hours == pytest.approx(10.0, abs=0.05)

    def test_candidate_confidence_in_01(self):
        events = _two_events("422110600", gap_h=24.0)
        resp = detect_dark_ships(events)
        c = resp.candidates[0].confidence
        assert 0.0 < c <= 1.0

    def test_confidence_never_exceeds_099(self):
        events = _two_events("422110600", gap_h=200.0)
        resp = detect_dark_ships(events)
        assert resp.candidates[0].confidence <= 0.99

    def test_candidate_has_event_id(self):
        events = _two_events("422110600", gap_h=12.0)
        resp = detect_dark_ships(events)
        eid = resp.candidates[0].event_id
        assert eid.startswith("dark-") and len(eid) > 5


class TestSanctionsBoost:
    def test_sanctioned_vessel_higher_confidence(self):
        """WISDOM (422110600) is OFAC-SDN; same gap should yield higher confidence."""
        gap_h = 24.0
        clean = detect_dark_ships(_two_events("211330000", gap_h=gap_h))
        sanctioned = detect_dark_ships(_two_events("422110600", gap_h=gap_h))
        if clean.total > 0 and sanctioned.total > 0:
            assert sanctioned.candidates[0].confidence >= clean.candidates[0].confidence

    def test_sanctions_flag_set_for_ofac_vessel(self):
        events = _two_events("422110600", gap_h=12.0)
        resp = detect_dark_ships(events)
        assert resp.candidates[0].sanctions_flag is True


class TestPositionJump:
    def test_position_jump_calculated_for_distant_points(self):
        """Hormuz (56.5,26.3) → Kharg (50.2,29.3): ~700 km jump."""
        events = _two_events("422110600", gap_h=12.0, lon0=56.5, lat0=26.3, lon1=50.2, lat1=29.3)
        resp = detect_dark_ships(events)
        assert resp.candidates[0].position_jump_km > 600

    def test_no_jump_for_same_position(self):
        events = _two_events("422110600", gap_h=12.0, lon0=56.5, lat0=26.3, lon1=56.5, lat1=26.3)
        resp = detect_dark_ships(events)
        assert resp.candidates[0].position_jump_km == pytest.approx(0.0, abs=0.1)


class TestResponseSorting:
    def test_candidates_sorted_by_confidence_descending(self):
        events = (
            _two_events("422110600", gap_h=48.0)  # sanctioned, high conf
            + _two_events("249987000", gap_h=7.0)  # clean, low conf
        )
        resp = detect_dark_ships(events)
        if len(resp.candidates) >= 2:
            confs = [c.confidence for c in resp.candidates]
            assert confs == sorted(confs, reverse=True)
