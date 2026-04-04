"""Integration tests for Phase 4 camera and detection HTTP endpoints.

Uses FastAPI TestClient against the full ARGUS app (app.main).
Tests all routes added in Phase 4:
  - /api/v1/cameras
  - /api/v1/cameras/{camera_id}
  - /api/v1/cameras/{camera_id}/observations
  - /api/v1/cameras/{camera_id}/clips
  - /api/v1/detections
  - /api/v1/detections/{detection_id}
  - /api/v1/detections/{detection_id}/evidence
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.cache.client import CacheClient
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker


# ── Shared TestClient fixture (module-scoped for speed) ──────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    reg = ProviderRegistry()
    reg.register(DemoProvider())
    dependencies.set_registry(reg)
    dependencies.set_cache(CacheClient())
    dependencies.set_breaker(CircuitBreaker())
    from app.main import app
    from app.resilience.rate_limiter import limiter
    limiter.reset()
    return TestClient(app, raise_server_exceptions=True)


# ── Known seeded IDs ──────────────────────────────────────────────────────────

_KNOWN_CAMERA_ID = "cam-hormuz-01"
_KNOWN_DETECTION_ID = "det-001"


# ──────────────────────────────────────────────────────────────────────────────
# Camera listing — GET /api/v1/cameras
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraListing:
    def test_list_cameras_returns_200(self, client: TestClient):
        r = client.get("/api/v1/cameras")
        assert r.status_code == 200

    def test_list_cameras_returns_items(self, client: TestClient):
        r = client.get("/api/v1/cameras")
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_camera_item_has_required_fields(self, client: TestClient):
        r = client.get("/api/v1/cameras")
        item = r.json()[0]
        assert "camera_id" in item
        assert "camera_type" in item
        assert "geo_registration" in item


# ──────────────────────────────────────────────────────────────────────────────
# Single camera — GET /api/v1/cameras/{camera_id}
# ──────────────────────────────────────────────────────────────────────────────


class TestSingleCamera:
    def test_get_camera_by_id_returns_200(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}")
        assert r.status_code == 200

    def test_get_camera_by_id_returns_correct_id(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}")
        assert r.json()["camera_id"] == _KNOWN_CAMERA_ID

    def test_get_camera_invalid_id_returns_404(self, client: TestClient):
        r = client.get("/api/v1/cameras/NONEXISTENT-CAMERA-XYZ")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Camera observations — GET /api/v1/cameras/{camera_id}/observations
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraObservations:
    def test_get_camera_observations_returns_200(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}/observations")
        assert r.status_code == 200

    def test_camera_observations_have_fields(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}/observations")
        body = r.json()
        assert len(body) >= 1
        for item in body:
            assert "observation_id" in item
            assert "camera_id" in item
            assert "observed_at" in item
            assert "confidence" in item

    def test_camera_observations_limit_param(self, client: TestClient):
        r = client.get(
            f"/api/v1/cameras/{_KNOWN_CAMERA_ID}/observations?limit=1"
        )
        assert r.status_code == 200
        assert len(r.json()) <= 1

    def test_camera_observations_unknown_camera_404(self, client: TestClient):
        r = client.get("/api/v1/cameras/NONEXISTENT-XYZ/observations")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Camera clips — GET /api/v1/cameras/{camera_id}/clips
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraClips:
    def test_get_camera_clips_returns_200(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}/clips")
        assert r.status_code == 200

    def test_camera_clips_have_url(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}/clips")
        body = r.json()
        assert len(body) >= 1
        for clip in body:
            assert "url" in clip
            assert clip["url"] != ""

    def test_camera_clips_is_loopable(self, client: TestClient):
        r = client.get(f"/api/v1/cameras/{_KNOWN_CAMERA_ID}/clips")
        body = r.json()
        assert len(body) >= 1
        for clip in body:
            assert "is_loopable" in clip

    def test_camera_clips_unknown_camera_404(self, client: TestClient):
        r = client.get("/api/v1/cameras/NONEXISTENT-XYZ/clips")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Detections — GET /api/v1/detections
# ──────────────────────────────────────────────────────────────────────────────


class TestDetectionsList:
    def test_list_detections_returns_200(self, client: TestClient):
        r = client.get("/api/v1/detections")
        assert r.status_code == 200

    def test_detections_have_geo_fields(self, client: TestClient):
        r = client.get("/api/v1/detections")
        body = r.json()
        with_geo = [d for d in body if d.get("geo_location") is not None]
        assert len(with_geo) >= 1
        for det in with_geo:
            assert "lon" in det["geo_location"]
            assert "lat" in det["geo_location"]

    def test_detections_confidence_range(self, client: TestClient):
        r = client.get("/api/v1/detections")
        body = r.json()
        assert len(body) >= 1
        for det in body:
            assert 0.0 <= det["confidence"] <= 1.0

    def test_list_detections_filter_type(self, client: TestClient):
        r = client.get("/api/v1/detections?detection_type=vehicle")
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 1
        for det in body:
            assert det["detection_type"] == "vehicle"

    def test_list_detections_filter_confidence(self, client: TestClient):
        r = client.get("/api/v1/detections?confidence_min=0.9")
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 1
        for det in body:
            assert det["confidence"] >= 0.9


# ──────────────────────────────────────────────────────────────────────────────
# Single detection — GET /api/v1/detections/{detection_id}
# ──────────────────────────────────────────────────────────────────────────────


class TestSingleDetection:
    def test_get_detection_by_id_returns_200(self, client: TestClient):
        r = client.get(f"/api/v1/detections/{_KNOWN_DETECTION_ID}")
        assert r.status_code == 200

    def test_get_detection_by_id_has_correct_id(self, client: TestClient):
        r = client.get(f"/api/v1/detections/{_KNOWN_DETECTION_ID}")
        assert r.json()["detection_id"] == _KNOWN_DETECTION_ID

    def test_get_detection_invalid_id_404(self, client: TestClient):
        r = client.get("/api/v1/detections/NONEXISTENT-DET-XYZ")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Evidence — POST /api/v1/detections/{detection_id}/evidence
# ──────────────────────────────────────────────────────────────────────────────


class TestDetectionEvidence:
    def test_post_detection_evidence_returns_200(self, client: TestClient):
        payload = {
            "evidence_id": "ev-camera-routes-test-001",
            "event_id": _KNOWN_DETECTION_ID,
            "evidence_type": "imagery",
        }
        r = client.post(
            f"/api/v1/detections/{_KNOWN_DETECTION_ID}/evidence",
            json=payload,
        )
        assert r.status_code == 200

    def test_post_detection_evidence_updates_evidence_refs(self, client: TestClient):
        evidence_id = "ev-camera-routes-test-002"
        payload = {
            "evidence_id": evidence_id,
            "event_id": _KNOWN_DETECTION_ID,
            "evidence_type": "report",
        }
        r = client.post(
            f"/api/v1/detections/{_KNOWN_DETECTION_ID}/evidence",
            json=payload,
        )
        assert r.status_code == 200
        body = r.json()
        assert evidence_id in body["evidence_refs"]

    def test_post_detection_evidence_idempotent(self, client: TestClient):
        evidence_id = "ev-camera-routes-test-003"
        payload = {
            "evidence_id": evidence_id,
            "event_id": _KNOWN_DETECTION_ID,
            "evidence_type": "imagery",
        }
        r1 = client.post(
            f"/api/v1/detections/{_KNOWN_DETECTION_ID}/evidence",
            json=payload,
        )
        r2 = client.post(
            f"/api/v1/detections/{_KNOWN_DETECTION_ID}/evidence",
            json=payload,
        )
        refs1 = r1.json()["evidence_refs"]
        refs2 = r2.json()["evidence_refs"]
        # Duplicate evidence_id must not be appended twice
        assert refs1.count(evidence_id) == 1
        assert refs2.count(evidence_id) == 1

    def test_post_detection_evidence_unknown_detection_404(
        self, client: TestClient
    ):
        payload = {
            "evidence_id": "ev-orphan-001",
            "event_id": "NONEXISTENT",
            "evidence_type": "imagery",
        }
        r = client.post(
            "/api/v1/detections/NONEXISTENT/evidence",
            json=payload,
        )
        assert r.status_code == 404
