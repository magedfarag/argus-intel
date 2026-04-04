"""Tests for P4-1 Change Detection Job System + P4-2 Analyst Review Workflow.

Coverage:
  P4-1.2  submit_job — state machine, candidate count, job retrieval
  P4-1.3  scoring fields on ChangeCandidate (confidence, change_class, ndvi_delta)
  P4-1.4  auto-generated scene pair metadata
  P4-2.1  list_pending_reviews — full list + AOI filter
  P4-2.2  review_candidate — confirmed / dismissed transitions, idempotency
  P4-2.3  validation: ReviewRequest rejecting 'pending' disposition
  P4-2.4  correlate — spatial + temporal filtering with a mock EventStore
  P4-2.5  build_evidence_pack — fields, correlated events inlined
  Router  smoke tests for all 7 endpoints via TestClient
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.analytics import (
    ChangeCandidate,
    ChangeClass,
    ChangeDetectionJobRequest,
    ChangeDetectionJobState,
    CorrelationRequest,
    ReviewRequest,
    ReviewStatus,
)
from src.services.change_analytics import (
    ChangeAnalyticsService,
    _flat_area_km2,
    _haversine_km,
    _bbox_from_geometry,
    _generate_synthetic_candidates,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

POLYGON_RIYADH = {
    "type": "Polygon",
    "coordinates": [
        [
            [46.60, 24.55],
            [46.80, 24.55],
            [46.80, 24.75],
            [46.60, 24.75],
            [46.60, 24.55],
        ]
    ],
}


def _make_request(**overrides: Any) -> ChangeDetectionJobRequest:
    defaults: Dict[str, Any] = {
        "geometry": POLYGON_RIYADH,
        "start_date": "2026-01-01",
        "end_date": "2026-02-28",
    }
    defaults.update(overrides)
    return ChangeDetectionJobRequest(**defaults)


@pytest.fixture()
def svc() -> ChangeAnalyticsService:
    return ChangeAnalyticsService()


# ── Utility function tests ─────────────────────────────────────────────────────

class TestUtilities:
    def test_bbox_from_polygon(self) -> None:
        bbox = _bbox_from_geometry(POLYGON_RIYADH)
        assert bbox == (46.60, 24.55, 46.80, 24.75)

    def test_bbox_from_empty_geometry(self) -> None:
        # Should not raise, returns fallback
        bbox = _bbox_from_geometry({})
        assert len(bbox) == 4

    def test_flat_area_positive(self) -> None:
        area = _flat_area_km2((46.60, 24.55, 46.80, 24.75))
        assert area > 0

    def test_haversine_zero(self) -> None:
        assert _haversine_km(46.7, 24.65, 46.7, 24.65) == pytest.approx(0.0, abs=1e-9)

    def test_haversine_known_distance(self) -> None:
        # Riyadh → Dubai ~850 km
        dist = _haversine_km(46.7, 24.7, 55.3, 25.2)
        assert 800 <= dist <= 900

    def test_generate_synthetic_candidates_count(self) -> None:
        candidates = _generate_synthetic_candidates(
            job_id="j-test",
            aoi_id="aoi-1",
            bbox=(46.60, 24.55, 46.80, 24.75),
            before_date="2026-01-01",
            after_date="2026-02-28",
        )
        assert len(candidates) == 3

    def test_synthetic_candidates_have_valid_fields(self) -> None:
        candidates = _generate_synthetic_candidates(
            job_id="j-test",
            aoi_id=None,
            bbox=(46.60, 24.55, 46.80, 24.75),
            before_date="2026-01-01",
            after_date="2026-02-28",
        )
        for c in candidates:
            assert 0.0 <= c.confidence <= 1.0
            assert c.review_status == ReviewStatus.PENDING
            assert c.ndvi_delta is not None and c.ndvi_delta < 0
            assert c.area_km2 >= 0


# ── P4-1.2 Job submission ─────────────────────────────────────────────────────

class TestSubmitJob:
    def test_job_state_completed(self, svc: ChangeAnalyticsService) -> None:
        req = _make_request()
        job = svc.submit_job(req)
        assert job.state == ChangeDetectionJobState.COMPLETED

    def test_job_id_is_unique(self, svc: ChangeAnalyticsService) -> None:
        j1 = svc.submit_job(_make_request())
        j2 = svc.submit_job(_make_request())
        assert j1.job_id != j2.job_id

    def test_job_has_candidates(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        assert len(job.candidates) >= 1

    def test_job_stats_candidate_count(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        assert job.stats["candidate_count"] == len(job.candidates)

    def test_get_job_returns_same_object(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        retrieved = svc.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    def test_get_job_unknown_returns_none(self, svc: ChangeAnalyticsService) -> None:
        assert svc.get_job("nonexistent") is None

    def test_aoi_id_propagated_to_candidates(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request(aoi_id="my-aoi"))
        for c in job.candidates:
            assert c.aoi_id == "my-aoi"


# ── P4-1.3 Scoring fields ─────────────────────────────────────────────────────

class TestCandidateScoring:
    def test_confidence_in_range(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        for c in job.candidates:
            assert 0.0 <= c.confidence <= 1.0

    def test_change_class_is_valid_enum(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        valid = {cc.value for cc in ChangeClass}
        for c in job.candidates:
            assert c.change_class.value in valid

    def test_rationale_non_empty(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        for c in job.candidates:
            assert len(c.rationale) >= 1


# ── P4-1.4 Scene pair ────────────────────────────────────────────────────────

class TestScenePair:
    def test_scene_pair_has_dates(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        assert job.scene_pair is not None
        assert "before_date" in job.scene_pair
        assert "after_date" in job.scene_pair

    def test_scene_pair_dates_match_request(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(
            _make_request(start_date="2025-12-01", end_date="2026-01-31")
        )
        assert job.scene_pair["before_date"] == "2025-12-01"
        assert job.scene_pair["after_date"] == "2026-01-31"


# ── P4-2.1 Pending review list ────────────────────────────────────────────────

class TestPendingReview:
    def test_all_new_candidates_are_pending(
        self, svc: ChangeAnalyticsService
    ) -> None:
        svc.submit_job(_make_request(aoi_id="aoi-x"))
        pending = svc.list_pending_reviews()
        assert len(pending) >= 3

    def test_aoi_filter(self, svc: ChangeAnalyticsService) -> None:
        svc.submit_job(_make_request(aoi_id="aoi-A"))
        svc.submit_job(_make_request(aoi_id="aoi-B"))
        only_a = svc.list_pending_reviews(aoi_id="aoi-A")
        for c in only_a:
            assert c.aoi_id == "aoi-A"

    def test_sorted_by_confidence_desc(
        self, svc: ChangeAnalyticsService
    ) -> None:
        svc.submit_job(_make_request())
        pending = svc.list_pending_reviews()
        confs = [c.confidence for c in pending]
        assert confs == sorted(confs, reverse=True)


# ── P4-2.2 Analyst review ─────────────────────────────────────────────────────

class TestReview:
    def test_confirm_candidate(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        cid = job.candidates[0].candidate_id
        updated = svc.review_candidate(
            cid, ReviewRequest(disposition=ReviewStatus.CONFIRMED, notes="Verified on-site")
        )
        assert updated is not None
        assert updated.review_status == ReviewStatus.CONFIRMED
        assert updated.analyst_notes == "Verified on-site"
        assert updated.reviewed_at is not None

    def test_dismiss_candidate(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        cid = job.candidates[1].candidate_id
        updated = svc.review_candidate(
            cid, ReviewRequest(disposition=ReviewStatus.DISMISSED)
        )
        assert updated is not None
        assert updated.review_status == ReviewStatus.DISMISSED

    def test_reviewed_candidate_removed_from_pending(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request())
        cid = job.candidates[0].candidate_id
        svc.review_candidate(cid, ReviewRequest(disposition=ReviewStatus.CONFIRMED))
        pending_ids = {c.candidate_id for c in svc.list_pending_reviews()}
        assert cid not in pending_ids

    def test_review_unknown_candidate_returns_none(
        self, svc: ChangeAnalyticsService
    ) -> None:
        result = svc.review_candidate(
            "no-such-id", ReviewRequest(disposition=ReviewStatus.CONFIRMED)
        )
        assert result is None

    def test_review_request_rejects_pending_disposition(self) -> None:
        with pytest.raises(Exception):
            ReviewRequest(disposition=ReviewStatus.PENDING)

    def test_job_stats_updated_after_review(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request())
        initial_pending = job.stats["pending_review"]
        cid = job.candidates[0].candidate_id
        svc.review_candidate(cid, ReviewRequest(disposition=ReviewStatus.CONFIRMED))
        updated_job = svc.get_job(job.job_id)
        assert updated_job is not None
        assert updated_job.stats["pending_review"] == initial_pending - 1


# ── P4-2.4 Correlation ────────────────────────────────────────────────────────

class TestCorrelation:
    def _make_mock_event(
        self, event_id: str, lon: float, lat: float, offset_hours: float = 0.0
    ) -> MagicMock:
        ev = MagicMock()
        ev.event_id = event_id
        ev.centroid = {"lon": lon, "lat": lat}
        # Anchor to now() so the time window check always passes by default
        ev.event_time = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
        ev.event_type = MagicMock()
        ev.event_type.value = "contextual_event"
        return ev

    def _make_mock_store(self, events: list) -> MagicMock:
        store = MagicMock()
        store._lock = __import__("threading").Lock()
        store._events = {e.event_id: e for e in events}
        return store

    def test_correlation_finds_nearby_events(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request())
        cand = job.candidates[0]

        # Build events — one nearby, one far away
        nearby = self._make_mock_event(
            "ev-near",
            cand.center["lon"] + 0.01,
            cand.center["lat"] + 0.01,
        )
        far_away = self._make_mock_event("ev-far", 0.0, 0.0)
        store = self._make_mock_store([nearby, far_away])

        result = svc.correlate(
            CorrelationRequest(
                candidate_id=cand.candidate_id,
                search_radius_km=100.0,
                time_window_hours=720.0,
            ),
            event_store=store,
        )
        assert result is not None
        assert "ev-near" in result.correlated_event_ids
        assert "ev-far" not in result.correlated_event_ids

    def test_correlation_time_filter(self, svc: ChangeAnalyticsService) -> None:
        job = svc.submit_job(_make_request())
        cand = job.candidates[0]

        # Event is spatially nearby but outside the time window
        ev = self._make_mock_event(
            "ev-stale",
            cand.center["lon"] + 0.01,
            cand.center["lat"] + 0.01,
            offset_hours=-99999.0,  # way in the past
        )
        store = self._make_mock_store([ev])

        result = svc.correlate(
            CorrelationRequest(
                candidate_id=cand.candidate_id,
                search_radius_km=100.0,
                time_window_hours=1.0,  # tight window
            ),
            event_store=store,
        )
        assert result is not None
        assert "ev-stale" not in result.correlated_event_ids

    def test_correlation_unknown_candidate_returns_none(
        self, svc: ChangeAnalyticsService
    ) -> None:
        store = self._make_mock_store([])
        result = svc.correlate(
            CorrelationRequest(candidate_id="no-such", search_radius_km=1.0),
            event_store=store,
        )
        assert result is None

    def test_correlation_persisted_to_candidate(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request())
        cand = job.candidates[0]
        nearby = self._make_mock_event(
            "ev-persist",
            cand.center["lon"] + 0.01,
            cand.center["lat"] + 0.01,
        )
        store = self._make_mock_store([nearby])
        svc.correlate(
            CorrelationRequest(
                candidate_id=cand.candidate_id,
                search_radius_km=100.0,
                time_window_hours=720.0,
            ),
            event_store=store,
        )
        updated = svc.get_candidate(cand.candidate_id)
        assert updated is not None
        assert "ev-persist" in updated.correlated_event_ids


# ── P4-2.5 Evidence pack ─────────────────────────────────────────────────────

class TestEvidencePack:
    def test_evidence_pack_fields_populated(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request())
        cand = job.candidates[0]
        pack = svc.build_evidence_pack(cand.candidate_id)
        assert pack is not None
        assert pack.candidate_id == cand.candidate_id
        assert pack.job_id == job.job_id
        assert pack.change_class == cand.change_class
        assert pack.schema_version == "1.0"

    def test_evidence_pack_unknown_candidate_returns_none(
        self, svc: ChangeAnalyticsService
    ) -> None:
        assert svc.build_evidence_pack("no-such-id") is None

    def test_evidence_pack_includes_correlated_events(
        self, svc: ChangeAnalyticsService
    ) -> None:
        job = svc.submit_job(_make_request())
        cand = job.candidates[0]

        # Inject a correlated event manually
        ev_id = "ev-evidence"

        mock_ev = MagicMock()
        mock_ev.model_dump.return_value = {"event_id": ev_id, "source": "gdelt"}

        from unittest.mock import patch, MagicMock as MM
        store = MM()
        store.get.side_effect = lambda eid: mock_ev if eid == ev_id else None

        # Manually set correlated_event_ids on the stored candidate
        from src.services.change_analytics import ChangeAnalyticsService as _S
        with svc._lock:
            current = svc._candidates[cand.candidate_id]
            svc._candidates[cand.candidate_id] = current.model_copy(
                update={"correlated_event_ids": [ev_id]}
            )

        pack = svc.build_evidence_pack(cand.candidate_id, event_store=store)
        assert pack is not None
        assert len(pack.correlated_events) == 1
        assert pack.correlated_events[0]["event_id"] == ev_id


# ── Router smoke tests ────────────────────────────────────────────────────────

class TestAnalyticsRouter:
    """Smoke tests via TestClient covering all 7 analytics endpoints."""

    @pytest.fixture(autouse=True)
    def _client(self) -> None:
        from app.main import app
        from src.api.analytics import set_analytics_service
        self.svc = ChangeAnalyticsService()
        set_analytics_service(self.svc)
        self.client = TestClient(app, raise_server_exceptions=True)

    def _create_job(self) -> Dict[str, Any]:
        resp = self.client.post(
            "/api/v1/analytics/change-detection",
            json={
                "geometry": POLYGON_RIYADH,
                "start_date": "2026-01-01",
                "end_date": "2026-02-28",
            },
        )
        assert resp.status_code == 202, resp.text
        return resp.json()

    def test_submit_returns_202(self) -> None:
        resp = self.client.post(
            "/api/v1/analytics/change-detection",
            json={
                "geometry": POLYGON_RIYADH,
                "start_date": "2026-01-01",
                "end_date": "2026-02-28",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["state"] == "completed"

    def test_get_job_200(self) -> None:
        job = self._create_job()
        resp = self.client.get(f"/api/v1/analytics/change-detection/{job['job_id']}")
        assert resp.status_code == 200

    def test_get_job_404(self) -> None:
        resp = self.client.get("/api/v1/analytics/change-detection/nonexistent")
        assert resp.status_code == 404

    def test_get_candidates_200(self) -> None:
        job = self._create_job()
        resp = self.client.get(
            f"/api/v1/analytics/change-detection/{job['job_id']}/candidates"
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_pending_review_200(self) -> None:
        self._create_job()
        resp = self.client.get("/api/v1/analytics/review")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_review_candidate_200(self) -> None:
        job = self._create_job()
        cid = job["candidates"][0]["candidate_id"]
        resp = self.client.put(
            f"/api/v1/analytics/change-detection/{cid}/review",
            json={"disposition": "confirmed", "notes": "Confirmed via aerial survey"},
        )
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "confirmed"

    def test_review_candidate_404(self) -> None:
        resp = self.client.put(
            "/api/v1/analytics/change-detection/no-such/review",
            json={"disposition": "confirmed"},
        )
        assert resp.status_code == 404

    def test_correlation_200(self) -> None:
        job = self._create_job()
        cid = job["candidates"][0]["candidate_id"]
        resp = self.client.post(
            "/api/v1/analytics/correlation",
            json={
                "candidate_id": cid,
                "search_radius_km": 50.0,
                "time_window_hours": 720.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate_id"] == cid
        assert "correlated_event_ids" in data

    def test_correlation_404(self) -> None:
        resp = self.client.post(
            "/api/v1/analytics/correlation",
            json={
                "candidate_id": "no-such",
                "search_radius_km": 5.0,
            },
        )
        assert resp.status_code == 404

    def test_evidence_pack_200(self) -> None:
        job = self._create_job()
        cid = job["candidates"][0]["candidate_id"]
        resp = self.client.get(
            f"/api/v1/analytics/change-detection/{cid}/evidence-pack"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate_id"] == cid
        assert data["schema_version"] == "1.0"

    def test_evidence_pack_404(self) -> None:
        resp = self.client.get(
            "/api/v1/analytics/change-detection/no-such/evidence-pack"
        )
        assert resp.status_code == 404

    def test_submit_missing_aoi_and_geometry_422(self) -> None:
        resp = self.client.post(
            "/api/v1/analytics/change-detection",
            json={"start_date": "2026-01-01", "end_date": "2026-02-28"},
        )
        assert resp.status_code == 422

    def test_aoi_id_only_accepted(self) -> None:
        resp = self.client.post(
            "/api/v1/analytics/change-detection",
            json={
                "aoi_id": "some-aoi",
                "start_date": "2026-01-01",
                "end_date": "2026-02-28",
            },
        )
        # aoi_id without geometry still valid — service will use fallback bbox
        assert resp.status_code == 202
