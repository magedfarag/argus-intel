"""Unit tests for DemoProvider."""
from __future__ import annotations
from datetime import date
import pytest
from app.providers.demo import DemoProvider, _polygon_area_km2, SCENARIOS, MIN_AREA_KM2, MAX_AREA_KM2

RING = [[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]

def test_polygon_area_reasonable():
    area = _polygon_area_km2(RING)
    assert 1.0 < area < 200.0

def test_polygon_area_min_coords_raises():
    with pytest.raises(ValueError):
        _polygon_area_km2([[0, 0], [1, 0], [0, 0]])

def test_demo_credentials_always_valid():
    ok, _ = DemoProvider().validate_credentials()
    assert ok is True

def test_demo_healthcheck_ok():
    ok, _ = DemoProvider().healthcheck()
    assert ok is True

def test_demo_search_returns_two_scenes():
    scenes = DemoProvider().search_imagery(
        geometry={"type": "Polygon", "coordinates": [RING]},
        start_date="2026-03-01", end_date="2026-03-28",
    )
    assert len(scenes) == 2

def test_demo_generate_changes_full_window():
    changes = DemoProvider().generate_changes([30.0, 50.0, 30.1, 50.1], date(2026, 3, 1), date(2026, 3, 28))
    assert len(changes) == len(SCENARIOS)
    for c in changes:
        assert "change_type" in c and "confidence" in c

def test_demo_generate_changes_empty_outside_window():
    changes = DemoProvider().generate_changes([30.0, 50.0, 30.1, 50.1], date(2026, 1, 1), date(2026, 1, 15))
    assert changes == []

def test_demo_capabilities():
    caps = DemoProvider().get_capabilities()
    assert caps.get("is_demo") is True
