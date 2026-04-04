"""Unit tests for P6-1 chokepoint service.

Tests: data integrity, threat levels, trend values, geometry, metrics,
determinism, and ChokepointListResponse wrapping.
"""
from __future__ import annotations

import pytest
from src.services.chokepoint_service import (
    Chokepoint,
    ChokepointListResponse,
    ChokepointMetric,
    ChokepointMetricsResponse,
    get_all_chokepoints,
    get_chokepoint,
    get_chokepoint_metrics,
)


@pytest.fixture
def all_chokepoints() -> list[Chokepoint]:
    return get_all_chokepoints()


class TestGetAllChokepoints:
    def test_returns_four_chokepoints(self, all_chokepoints):
        assert len(all_chokepoints) == 4

    def test_ids_are_unique(self, all_chokepoints):
        ids = [cp.id for cp in all_chokepoints]
        assert len(ids) == len(set(ids))

    def test_hormuz_is_present(self, all_chokepoints):
        ids = {cp.id for cp in all_chokepoints}
        assert "hormuz" in ids

    def test_bab_el_mandeb_is_present(self, all_chokepoints):
        ids = {cp.id for cp in all_chokepoints}
        assert "bab-el-mandeb" in ids

    def test_suez_is_present(self, all_chokepoints):
        ids = {cp.id for cp in all_chokepoints}
        assert "suez" in ids

    def test_malacca_is_present(self, all_chokepoints):
        ids = {cp.id for cp in all_chokepoints}
        assert "malacca" in ids

    def test_threat_levels_in_range(self, all_chokepoints):
        for cp in all_chokepoints:
            assert 1 <= cp.threat_level <= 5, f"{cp.id} threat_level out of range"

    def test_threat_labels_valid(self, all_chokepoints):
        valid = {"LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"}
        for cp in all_chokepoints:
            assert cp.threat_label in valid, f"{cp.id} has invalid threat_label {cp.threat_label}"

    def test_trend_values_valid(self, all_chokepoints):
        for cp in all_chokepoints:
            assert cp.trend in {"+", "-", "="}, f"{cp.id} has invalid trend {cp.trend}"

    def test_daily_flow_positive(self, all_chokepoints):
        for cp in all_chokepoints:
            assert cp.daily_flow_mbbl > 0

    def test_vessel_count_non_negative(self, all_chokepoints):
        for cp in all_chokepoints:
            assert cp.vessel_count_24h >= 0

    def test_geometry_is_polygon(self, all_chokepoints):
        for cp in all_chokepoints:
            assert cp.geometry["type"] == "Polygon"
            assert len(cp.geometry["coordinates"][0]) >= 4  # ring has coords

    def test_centroid_lon_in_range(self, all_chokepoints):
        for cp in all_chokepoints:
            assert -180 <= cp.centroid["lon"] <= 180

    def test_centroid_lat_in_range(self, all_chokepoints):
        for cp in all_chokepoints:
            assert -90 <= cp.centroid["lat"] <= 90

    def test_description_non_empty(self, all_chokepoints):
        for cp in all_chokepoints:
            assert len(cp.description) > 20

    def test_hormuz_flow_exceeds_bab(self, all_chokepoints):
        cp_map = {cp.id: cp for cp in all_chokepoints}
        assert cp_map["hormuz"].daily_flow_mbbl > cp_map["bab-el-mandeb"].daily_flow_mbbl

    def test_determinism(self):
        """Repeated calls return identical data."""
        a = get_all_chokepoints()
        b = get_all_chokepoints()
        for ca, cb in zip(a, b):
            assert ca.id == cb.id
            assert ca.threat_level == cb.threat_level
            assert ca.daily_flow_mbbl == cb.daily_flow_mbbl


class TestGetChokepoint:
    def test_known_id_returns_chokepoint(self):
        cp = get_chokepoint("hormuz")
        assert cp is not None
        assert cp.id == "hormuz"

    def test_unknown_id_returns_none(self):
        assert get_chokepoint("does-not-exist") is None

    def test_returned_object_is_chokepoint_instance(self):
        cp = get_chokepoint("malacca")
        assert isinstance(cp, Chokepoint)


class TestChokepointListResponse:
    def test_wrapping(self):
        cps = get_all_chokepoints()
        resp = ChokepointListResponse(chokepoints=cps)
        assert len(resp.chokepoints) == 4


class TestGetChokepointMetrics:
    def test_returns_30_metrics(self):
        resp = get_chokepoint_metrics("hormuz")
        assert resp is not None
        assert len(resp.metrics) == 30

    def test_metrics_response_type(self):
        resp = get_chokepoint_metrics("hormuz")
        assert isinstance(resp, ChokepointMetricsResponse)

    def test_unknown_id_returns_none(self):
        assert get_chokepoint_metrics("unknown-id") is None

    def test_metric_dates_are_ordered(self):
        resp = get_chokepoint_metrics("hormuz")
        dates = [m.date for m in resp.metrics]
        assert dates == sorted(dates)

    def test_metric_flow_positive(self):
        resp = get_chokepoint_metrics("hormuz")
        for m in resp.metrics:
            assert m.daily_flow_mbbl > 0

    def test_metric_threat_level_in_range(self):
        resp = get_chokepoint_metrics("hormuz")
        for m in resp.metrics:
            assert 1 <= m.threat_level <= 5

    def test_metrics_deterministic(self):
        r1 = get_chokepoint_metrics("suez")
        r2 = get_chokepoint_metrics("suez")
        for m1, m2 in zip(r1.metrics, r2.metrics):
            assert m1.date == m2.date
            assert m1.daily_flow_mbbl == m2.daily_flow_mbbl
