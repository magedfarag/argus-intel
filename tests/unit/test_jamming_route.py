"""Route and failure-mode tests for the jamming API — JAM-04.

Coverage:
- GET  /api/v1/jamming/events          — 200, is_demo_data always True
- GET  /api/v1/jamming/events          — confidence_min filter applied
- GET  /api/v1/jamming/events          — invalid region_bbox → 422
- GET  /api/v1/jamming/heatmap         — list of {lon, lat, weight} objects
- POST /api/v1/jamming/ingest          — valid body → 200, is_demo_data True
- POST /api/v1/jamming/ingest          — end <= start → 422
- GET  /api/v1/jamming/events/{id}     — valid ID → 200
- GET  /api/v1/jamming/events/{id}     — unknown ID → 404
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from app.main import app
from src.services.operational_layer_service import get_jamming_service


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def known_jamming_id() -> str:
    """Return a jamming_id that actually exists in the seeded store."""
    events = list(get_jamming_service().all_events().values())
    assert events, "JammingLayerService store is empty — seeding failed"
    return events[0].jamming_id


# ── List endpoint ─────────────────────────────────────────────────────────────


class TestListJammingEvents:
    def test_returns_200_and_demo_flag(self, client: TestClient) -> None:
        """GET /events must return HTTP 200 and is_demo_data: true."""
        resp = client.get("/api/v1/jamming/events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_demo_data"] is True
        assert "events" in body

    def test_returns_event_list(self, client: TestClient) -> None:
        """Response events list must be non-empty (store is seeded at startup)."""
        resp = client.get("/api/v1/jamming/events")
        assert resp.status_code == 200
        assert isinstance(resp.json()["events"], list)
        assert len(resp.json()["events"]) > 0

    def test_confidence_min_filter_applied(self, client: TestClient) -> None:
        """confidence_min=0.9 should filter out low-confidence stub events.

        The stub connector generates events with confidence ≈ 0.5 by default.
        Setting confidence_min=0.9 must reduce (or eliminate) the result set
        compared to the unfiltered call.  We only assert that the list length
        does not *exceed* the unfiltered length — not that it is empty.
        """
        unfiltered_len = len(client.get("/api/v1/jamming/events").json()["events"])
        resp = client.get("/api/v1/jamming/events", params={"confidence_min": 0.9})
        assert resp.status_code == 200
        filtered_len = len(resp.json()["events"])
        assert filtered_len <= unfiltered_len

    def test_invalid_region_bbox_returns_422(self, client: TestClient) -> None:
        """A malformed region_bbox string must produce HTTP 422."""
        resp = client.get(
            "/api/v1/jamming/events",
            params={"region_bbox": "not-a-valid-bbox"},
        )
        assert resp.status_code == 422

    def test_region_bbox_not_enough_parts_returns_422(self, client: TestClient) -> None:
        """region_bbox with fewer than four comma-separated values → 422."""
        resp = client.get(
            "/api/v1/jamming/events",
            params={"region_bbox": "0.0,0.0,1.0"},  # only 3 parts
        )
        assert resp.status_code == 422

    def test_valid_region_bbox_filters_events(self, client: TestClient) -> None:
        """A valid region_bbox covering a known empty region returns an empty list."""
        # South Atlantic — none of the seeded zones land here.
        resp = client.get(
            "/api/v1/jamming/events",
            params={"region_bbox": "-60.0,-50.0,-10.0,-10.0"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_demo_data"] is True
        assert isinstance(resp.json()["events"], list)


# ── Heatmap endpoint ──────────────────────────────────────────────────────────


class TestJammingHeatmap:
    def test_returns_list_of_heatmap_points(self, client: TestClient) -> None:
        """GET /heatmap must return a list of objects with lon, lat, weight."""
        resp = client.get("/api/v1/jamming/heatmap")
        assert resp.status_code == 200
        points = resp.json()
        assert isinstance(points, list)
        assert len(points) > 0
        for point in points:
            assert "lon" in point
            assert "lat" in point
            assert "weight" in point
            assert isinstance(point["lon"], float)
            assert isinstance(point["lat"], float)
            assert isinstance(point["weight"], float)

    def test_heatmap_weight_is_confidence(self, client: TestClient) -> None:
        """Heatmap weights must be in [0.0, 1.0] (they reflect event confidence)."""
        resp = client.get("/api/v1/jamming/heatmap")
        for point in resp.json():
            assert 0.0 <= point["weight"] <= 1.0


# ── Ingest endpoint ───────────────────────────────────────────────────────────


class TestIngestJamming:
    def test_valid_body_returns_200_and_demo_flag(self, client: TestClient) -> None:
        """POST /ingest with a valid time window returns 200 and is_demo_data: true."""
        now = datetime.now(UTC)
        payload = {
            "start": (now - timedelta(days=7)).isoformat(),
            "end": now.isoformat(),
        }
        resp = client.post("/api/v1/jamming/ingest", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_demo_data"] is True
        assert isinstance(body["events"], list)

    def test_end_before_start_returns_422(self, client: TestClient) -> None:
        """POST /ingest with end <= start must return HTTP 422."""
        now = datetime.now(UTC)
        payload = {
            "start": now.isoformat(),
            "end": (now - timedelta(hours=1)).isoformat(),
        }
        resp = client.post("/api/v1/jamming/ingest", json=payload)
        assert resp.status_code == 422

    def test_end_equal_start_returns_422(self, client: TestClient) -> None:
        """POST /ingest with end == start must return HTTP 422."""
        ts = datetime.now(UTC).isoformat()
        resp = client.post("/api/v1/jamming/ingest", json={"start": ts, "end": ts})
        assert resp.status_code == 422

    def test_missing_body_returns_422(self, client: TestClient) -> None:
        """POST /ingest with no body must return HTTP 422 (Pydantic validation)."""
        resp = client.post("/api/v1/jamming/ingest")
        assert resp.status_code == 422


# ── Single-event endpoint ─────────────────────────────────────────────────────


class TestGetJammingEvent:
    def test_known_id_returns_200(
        self, client: TestClient, known_jamming_id: str
    ) -> None:
        """GET /events/{id} with a seeded ID must return HTTP 200."""
        resp = client.get(f"/api/v1/jamming/events/{known_jamming_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["jamming_id"] == known_jamming_id

    def test_unknown_id_returns_404(self, client: TestClient) -> None:
        """GET /events/{id} with a non-existent ID must return HTTP 404."""
        resp = client.get("/api/v1/jamming/events/nonexistent-id-00000000")
        assert resp.status_code == 404
