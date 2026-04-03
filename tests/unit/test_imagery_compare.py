"""Unit tests for the Imagery Compare Workflow (P2-3.4 — ≥5 tests).

Covers:
  - POST /api/v1/imagery/compare with valid before/after events
  - 404 when before or after event_id not found
  - 422 when temporal ordering is reversed
  - Quality rating heuristics (good / acceptable / poor)
  - Deterministic comparison_id
  - Cloud cover and cross-sensor notes
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.imagery import router as imagery_router, set_imagery_event_store
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.services.event_store import EventStore


# ── Helpers ───────────────────────────────────────────────────────────────────

_T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_T1 = _T0 + timedelta(days=14)  # 14-day gap → "good"


def _make_imagery_event(
    hours_offset: int = 0,
    cloud_cover: float = 5.0,
    source: str = "copernicus-cdse",
) -> CanonicalEvent:
    ts = _T0 + timedelta(hours=hours_offset)
    return CanonicalEvent(
        event_id=make_event_id(source, f"scene_{hours_offset}", ts.isoformat()),
        source=source,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        event_type=EventType.IMAGERY_ACQUISITION,
        event_time=ts,
        geometry={"type": "Polygon", "coordinates": [[[45, 24], [46, 24], [46, 25], [45, 24]]]},
        centroid={"type": "Point", "coordinates": [45.5, 24.5]},
        attributes={"cloud_cover_pct": cloud_cover, "platform": "Sentinel-2A"},
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="s3://bucket/test.json"),
        license=LicenseRecord(),
    )


@pytest.fixture
def compare_client():
    store = EventStore()
    before = _make_imagery_event(hours_offset=0, cloud_cover=10.0)
    after = _make_imagery_event(hours_offset=24 * 14, cloud_cover=5.0)
    store.ingest(before)
    store.ingest(after)
    set_imagery_event_store(store)
    app = FastAPI()
    app.include_router(imagery_router)
    return TestClient(app), before.event_id, after.event_id


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestImageryCompareEndpoint:
    def test_valid_compare_returns_200(self, compare_client):
        client, before_id, after_id = compare_client
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before_id, "after_event_id": after_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "comparison_id" in body
        assert "before_scene" in body
        assert "after_scene" in body
        assert "quality" in body

    def test_response_contains_temporal_gap(self, compare_client):
        client, before_id, after_id = compare_client
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before_id, "after_event_id": after_id},
        )
        body = resp.json()
        assert abs(body["quality"]["temporal_gap_days"] - 14.0) < 0.01

    def test_good_quality_rating_for_clear_14_day_gap(self, compare_client):
        client, before_id, after_id = compare_client
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before_id, "after_event_id": after_id},
        )
        assert resp.json()["quality"]["rating"] == "good"

    def test_404_when_before_event_missing(self, compare_client):
        client, _, after_id = compare_client
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": "nonexistent-before", "after_event_id": after_id},
        )
        assert resp.status_code == 404

    def test_404_when_after_event_missing(self, compare_client):
        client, before_id, _ = compare_client
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before_id, "after_event_id": "nonexistent-after"},
        )
        assert resp.status_code == 404

    def test_422_when_temporal_order_reversed(self, compare_client):
        """Passing after ID as before and vice versa must return 422."""
        client, before_id, after_id = compare_client
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": after_id, "after_event_id": before_id},
        )
        assert resp.status_code == 422

    def test_comparison_id_is_deterministic(self, compare_client):
        client, before_id, after_id = compare_client
        resp1 = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before_id, "after_event_id": after_id},
        )
        resp2 = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before_id, "after_event_id": after_id},
        )
        assert resp1.json()["comparison_id"] == resp2.json()["comparison_id"]


class TestImageryCompareQualityRatings:
    def _run_compare(
        self,
        gap_days: int = 14,
        cloud_before: float = 5.0,
        cloud_after: float = 5.0,
        source_before: str = "src-a",
        source_after: str = "src-a",
    ) -> dict:
        store = EventStore()
        before = _make_imagery_event(hours_offset=0, cloud_cover=cloud_before, source=source_before)
        after = _make_imagery_event(hours_offset=24 * gap_days, cloud_cover=cloud_after, source=source_after)
        # Ensure distinct event_ids even with same params
        store.ingest(before)
        store.ingest(after)
        set_imagery_event_store(store)
        app = FastAPI()
        app.include_router(imagery_router)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/imagery/compare",
            json={"before_event_id": before.event_id, "after_event_id": after.event_id},
        )
        return resp.json()

    def test_poor_rating_for_small_gap(self):
        body = self._run_compare(gap_days=1)
        assert body["quality"]["rating"] == "poor"

    def test_poor_rating_when_both_cloudy(self):
        body = self._run_compare(gap_days=14, cloud_before=50.0, cloud_after=50.0)
        assert body["quality"]["rating"] == "poor"

    def test_cross_sensor_note_present(self):
        body = self._run_compare(source_before="cdse", source_after="usgs-landsat")
        notes = body["quality"]["notes"]
        assert any("Cross-sensor" in n for n in notes)

    def test_small_gap_note_present(self):
        body = self._run_compare(gap_days=3)
        notes = body["quality"]["notes"]
        assert any("<7 days" in n for n in notes)
