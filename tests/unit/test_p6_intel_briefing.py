"""Unit tests for P6-6 intelligence briefing generator.

Tests: risk level derivation from chokepoints, response structure,
vessel alerts, key findings, determinism (shape), and chokepoint status summary.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from src.services.intel_briefing import (
    IntelBriefing,
    VesselAlert,
    generate_briefing,
)


@pytest.fixture(scope="module")
def briefing() -> IntelBriefing:
    return generate_briefing()


class TestBriefingShape:
    def test_returns_intel_briefing_instance(self, briefing):
        assert isinstance(briefing, IntelBriefing)

    def test_briefing_id_starts_with_brf(self, briefing):
        assert briefing.briefing_id.startswith("brf-")

    def test_timestamp_is_iso_string(self, briefing):
        # Must parse without error
        dt = datetime.fromisoformat(briefing.timestamp)
        assert dt.tzinfo is not None  # must be timezone-aware

    def test_classification_is_set(self, briefing):
        assert len(briefing.classification) > 5

    def test_executive_summary_non_empty(self, briefing):
        assert len(briefing.executive_summary) > 30


class TestRiskLevel:
    def test_risk_level_in_valid_set(self, briefing):
        assert briefing.risk_level in {"CRITICAL", "HIGH", "MODERATE", "LOW"}

    def test_risk_color_is_hex(self, briefing):
        assert briefing.risk_color.startswith("#")
        assert len(briefing.risk_color) == 7

    def test_risk_level_is_critical(self, briefing):
        """Bab-el-Mandeb is CRITICAL (threat_level=5), so briefing must be CRITICAL."""
        assert briefing.risk_level == "CRITICAL"

    def test_risk_color_is_red_for_critical(self, briefing):
        assert briefing.risk_color == "#dc2626"


class TestKeyFindings:
    def test_at_least_one_key_finding(self, briefing):
        assert len(briefing.key_findings) >= 1

    def test_all_key_findings_are_strings(self, briefing):
        for kf in briefing.key_findings:
            assert isinstance(kf, str)

    def test_dark_ship_finding_present(self, briefing):
        combined = " ".join(briefing.key_findings).lower()
        assert "dark" in combined or "ais" in combined


class TestVesselAlerts:
    def test_at_least_one_vessel_alert(self, briefing):
        assert len(briefing.vessel_alerts) >= 1

    def test_all_alerts_are_vessel_alert_instances(self, briefing):
        for a in briefing.vessel_alerts:
            assert isinstance(a, VesselAlert)

    def test_alert_confidence_in_range(self, briefing):
        for a in briefing.vessel_alerts:
            assert 0.0 < a.confidence <= 1.0

    def test_alert_types_valid(self, briefing):
        valid = {"dark_ship", "sanctions_entry", "position_jump"}
        for a in briefing.vessel_alerts:
            assert a.alert_type in valid

    def test_horse_alert_present(self, briefing):
        names = {a.vessel_name for a in briefing.vessel_alerts}
        assert "HORSE" in names

    def test_wisdom_alert_present(self, briefing):
        names = {a.vessel_name for a in briefing.vessel_alerts}
        assert "WISDOM" in names


class TestChokepointStatus:
    def test_four_chokepoints_in_status(self, briefing):
        assert len(briefing.chokepoint_status) == 4

    def test_status_entries_have_required_keys(self, briefing):
        required = {"id", "name", "threat_level", "threat_label", "daily_flow_mbbl", "trend"}
        for entry in briefing.chokepoint_status:
            assert required.issubset(entry.keys()), f"Missing keys in {entry}"

    def test_status_threat_levels_in_range(self, briefing):
        for entry in briefing.chokepoint_status:
            assert 1 <= entry["threat_level"] <= 5


class TestCounts:
    def test_dark_ship_count_non_negative(self, briefing):
        assert briefing.dark_ship_count >= 0

    def test_sanctioned_vessel_count_positive(self, briefing):
        assert briefing.sanctioned_vessel_count > 0

    def test_active_vessel_count_positive(self, briefing):
        assert briefing.active_vessel_count > 0


class TestDarkShipsApiDemoCandidates:
    """Test the curated demo candidates returned by the dark-ships API endpoint."""

    def test_demo_has_three_candidates(self):
        from src.api.dark_ships import list_demo_candidates
        resp = list_demo_candidates()
        assert resp.total == 3
        assert len(resp.candidates) == 3

    def test_demo_candidates_confidence_in_range(self):
        from src.api.dark_ships import list_demo_candidates
        resp = list_demo_candidates()
        for c in resp.candidates:
            assert 0.0 < c.confidence <= 1.0

    def test_demo_wisdom_present(self):
        from src.api.dark_ships import list_demo_candidates
        resp = list_demo_candidates()
        names = {c.vessel_name for c in resp.candidates}
        assert "WISDOM" in names

    def test_demo_horse_present(self):
        from src.api.dark_ships import list_demo_candidates
        resp = list_demo_candidates()
        names = {c.vessel_name for c in resp.candidates}
        assert "HORSE" in names

    def test_demo_sea_rose_present(self):
        from src.api.dark_ships import list_demo_candidates
        resp = list_demo_candidates()
        names = {c.vessel_name for c in resp.candidates}
        assert "SEA ROSE" in names

    def test_demo_gap_hours_above_threshold(self):
        from src.api.dark_ships import list_demo_candidates
        from src.services.dark_ship_detector import GAP_THRESHOLD_H
        resp = list_demo_candidates()
        for c in resp.candidates:
            assert c.gap_hours > GAP_THRESHOLD_H
