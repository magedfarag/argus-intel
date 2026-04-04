"""Unit tests for P6-2 vessel registry.

Tests: total count, MMSI/IMO lookups, sentinel None paths, filter flags.
"""
from __future__ import annotations

import pytest
from src.services.vessel_registry import (
    SanctionsStatus,
    VesselProfile,
    VesselType,
    get_vessel_by_imo,
    get_vessel_by_mmsi,
    list_vessels,
)


class TestListVessels:
    def test_returns_21_vessels_total(self):
        assert len(list_vessels()) == 21

    def test_returns_vessel_profile_instances(self):
        vessels = list_vessels()
        for v in vessels:
            assert isinstance(v, VesselProfile)

    def test_sanctions_only_filter_excludes_clean(self):
        results = list_vessels(sanctions_only=True)
        for v in results:
            assert v.sanctions_status != SanctionsStatus.CLEAN

    def test_sanctions_only_returns_non_empty(self):
        results = list_vessels(sanctions_only=True)
        assert len(results) > 0

    def test_dark_risk_critical_filter(self):
        results = list_vessels(dark_risk="critical")
        for v in results:
            assert v.dark_ship_risk == "critical"

    def test_dark_risk_low_filter(self):
        results = list_vessels(dark_risk="low")
        for v in results:
            assert v.dark_ship_risk == "low"

    def test_vessel_type_filter_vlcc(self):
        results = list_vessels(vessel_type="VLCC")
        for v in results:
            assert v.vessel_type == VesselType.VLCC

    def test_limit_applied(self):
        results = list_vessels(limit=5)
        assert len(results) == 5

    def test_limit_larger_than_set_returns_all(self):
        results = list_vessels(limit=1000)
        assert len(results) == 21

    def test_mmsis_are_unique(self):
        vessels = list_vessels()
        mmsis = [v.mmsi for v in vessels]
        assert len(mmsis) == len(set(mmsis))

    def test_all_vessels_have_names(self):
        for v in list_vessels():
            assert v.name.strip() != ""

    def test_all_vessels_have_valid_dark_risk(self):
        valid = {"low", "medium", "high", "critical", "unknown"}
        for v in list_vessels():
            assert v.dark_ship_risk in valid, f"{v.name} has invalid dark_ship_risk {v.dark_risk}"


class TestGetVesselByMmsi:
    def test_wisdom_found_by_mmsi(self):
        v = get_vessel_by_mmsi("422110600")
        assert v is not None
        assert v.name == "WISDOM"

    def test_wisdom_is_ofac_sdn(self):
        v = get_vessel_by_mmsi("422110600")
        assert v.sanctions_status == SanctionsStatus.OFAC_SDN

    def test_horse_is_shadow_fleet(self):
        v = get_vessel_by_mmsi("422110800")
        assert v is not None
        assert v.sanctions_status == SanctionsStatus.SHADOW_FLEET

    def test_saviz_is_supply_vessel(self):
        v = get_vessel_by_mmsi("422011200")
        assert v is not None
        assert v.vessel_type == VesselType.SUPPLY

    def test_clean_vessel_found(self):
        v = get_vessel_by_mmsi("211330000")
        assert v is not None
        assert v.sanctions_status == SanctionsStatus.CLEAN

    def test_unknown_mmsi_returns_none(self):
        assert get_vessel_by_mmsi("000000000") is None

    def test_empty_mmsi_returns_none(self):
        assert get_vessel_by_mmsi("") is None


class TestGetVesselByImo:
    def test_wisdom_by_imo(self):
        v = get_vessel_by_imo("9169501")
        assert v is not None
        assert v.name == "WISDOM"

    def test_unknown_imo_returns_none(self):
        assert get_vessel_by_imo("9999999") is None

    def test_patrol_craft_not_in_imo_index(self):
        """Patrol craft have IMO=N/A and must not be findable by IMO."""
        assert get_vessel_by_imo("N/A") is None

    def test_imo_and_mmsi_return_same_vessel(self):
        by_imo = get_vessel_by_imo("9169501")
        by_mmsi = get_vessel_by_mmsi("422110600")
        assert by_imo.name == by_mmsi.name
        assert by_imo.imo == by_mmsi.imo
