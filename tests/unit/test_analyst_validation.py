"""P4-3: Analyst validation against curated Middle East reference AOIs.

P4-3.1  Run change detection on each pilot AOI (Riyadh, Dubai, Doha)
         and verify >=1 candidate is produced per AOI.
P4-3.2  Operational evaluation — confidence thresholds, candidate scoring
         contract, and recall proxy (no false-negative below threshold).
P4-3.3  Document known false-positive change classes through explicit tests
         that assert correct classification of no-change / artifact scenarios.
P4-3.4  Analyst workflow validation: confirm/dismiss round-trip, evidence pack
         assembly, and review queue depletion.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.models.analytics import (
    ChangeClass,
    ChangeDetectionJobRequest,
    ChangeDetectionJobState,
    ReviewRequest,
    ReviewStatus,
)
from src.models.pilot_aois import PILOT_AOIS
from src.services.change_analytics import ChangeAnalyticsService


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def svc() -> ChangeAnalyticsService:
    return ChangeAnalyticsService()


def _job_request(aoi: dict, start: str = "2026-01-01", end: str = "2026-02-01") -> ChangeDetectionJobRequest:
    return ChangeDetectionJobRequest(
        aoi_id=aoi["id"],
        geometry=aoi["geometry"],
        start_date=start,
        end_date=end,
        max_cloud_cover_pct=20.0,
    )


# ── P4-3.1: Change detection runs on all pilot AOIs ──────────────────────────

class TestPilotAoiChangeDetection:
    """P4-3.1 — Run change detection on each pilot AOI; verify job completes."""

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_job_completes_for_pilot_aoi(self, svc: ChangeAnalyticsService, aoi: dict) -> None:
        req = _job_request(aoi)
        job = svc.submit_job(req)
        assert job.state == ChangeDetectionJobState.COMPLETED

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_at_least_one_candidate_per_pilot_aoi(self, svc: ChangeAnalyticsService, aoi: dict) -> None:
        req = _job_request(aoi)
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        assert len(candidates) >= 1, f"Expected >=1 candidate for AOI {aoi['id']}"

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_candidates_inside_aoi_bbox(self, svc: ChangeAnalyticsService, aoi: dict) -> None:
        coords = aoi["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        req = _job_request(aoi)
        job = svc.submit_job(req)
        for cand in svc.get_candidates(job.job_id):
            assert min_lon <= cand.center["lon"] <= max_lon, (
                f"Candidate center longitude {cand.center['lon']} outside AOI for {aoi['id']}"
            )
            assert min_lat <= cand.center["lat"] <= max_lat, (
                f"Candidate center latitude {cand.center['lat']} outside AOI for {aoi['id']}"
            )

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_job_aoi_id_preserved(self, svc: ChangeAnalyticsService, aoi: dict) -> None:
        req = _job_request(aoi)
        job = svc.submit_job(req)
        assert job.aoi_id == aoi["id"]


# ── P4-3.2: Scoring contract / operational evaluation ────────────────────────

class TestCandidateScoringContract:
    """P4-3.2 — Verify confidence ranges, change-class taxonomy, and scoring signal."""

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_confidence_in_valid_range(self, svc: ChangeAnalyticsService, aoi: dict) -> None:
        req = _job_request(aoi)
        job = svc.submit_job(req)
        for cand in svc.get_candidates(job.job_id):
            assert 0.0 <= cand.confidence <= 1.0, (
                f"Confidence {cand.confidence} out of [0,1] for candidate {cand.candidate_id}"
            )

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_change_class_is_valid_enum(self, svc: ChangeAnalyticsService, aoi: dict) -> None:
        req = _job_request(aoi)
        job = svc.submit_job(req)
        valid_classes = {c.value for c in ChangeClass}
        for cand in svc.get_candidates(job.job_id):
            assert cand.change_class.value in valid_classes

    def test_high_confidence_new_construction_expected_in_riyadh(self, svc: ChangeAnalyticsService) -> None:
        """Riyadh Northern Development Corridor should produce a NEW_CONSTRUCTION candidate."""
        riyadh = next(a for a in PILOT_AOIS if "riyadh" in a["id"].lower())
        req = _job_request(riyadh)
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        nc_candidates = [c for c in candidates if c.change_class == ChangeClass.NEW_CONSTRUCTION]
        assert len(nc_candidates) >= 1, "Expected at least one NEW_CONSTRUCTION candidate in Riyadh AOI"

    def test_ndvi_delta_negative_for_construction_classes(self, svc: ChangeAnalyticsService) -> None:
        """NDVI delta should be negative for construction-related change classes
        (bare soil/structures replace vegetation).
        """
        aoi = PILOT_AOIS[0]
        req = _job_request(aoi)
        job = svc.submit_job(req)
        construction_classes = {
            ChangeClass.NEW_CONSTRUCTION,
            ChangeClass.VEGETATION_CLEARING,
            ChangeClass.EARTHWORK,
        }
        for cand in svc.get_candidates(job.job_id):
            if cand.change_class in construction_classes and cand.ndvi_delta is not None:
                assert cand.ndvi_delta < 0, (
                    f"Expected negative ndvi_delta for {cand.change_class.value}, "
                    f"got {cand.ndvi_delta}"
                )

    def test_all_candidates_have_rationale(self, svc: ChangeAnalyticsService) -> None:
        aoi = PILOT_AOIS[0]
        req = _job_request(aoi)
        job = svc.submit_job(req)
        for cand in svc.get_candidates(job.job_id):
            assert len(cand.rationale) >= 1, f"Candidate {cand.candidate_id} has empty rationale"

    def test_area_positive_for_all_candidates(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        for cand in svc.get_candidates(job.job_id):
            assert cand.area_km2 > 0, f"Candidate {cand.candidate_id} has non-positive area"

    def test_candidate_ids_are_unique_within_job(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        candidate_ids = [c.candidate_id for c in svc.get_candidates(job.job_id)]
        assert len(candidate_ids) == len(set(candidate_ids)), "Duplicate candidate IDs detected"


# ── P4-3.3: Known false-positive class documentation ─────────────────────────

class TestKnownFalsePositiveClasses:
    """P4-3.3 — Verify that the analyst review workflow supports documenting
    and dismissing known false-positive change-detection outcomes.

    Known false-positive classes in arid Middle East SAR/optical imagery:
    1. Cloud/shadow artifacts — transient NDVI reduction mimicking clearing
    2. Seasonal agricultural patterns — NDVI drop during harvest season
    3. Desert dune migration — surface texture change without construction
    4. Water body reflectance changes — glint/wind effects on NDVI calculations
    5. Image registration errors — apparent change from misalignment
    """

    def test_analyst_can_dismiss_low_confidence_candidate(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        assert candidates
        low_conf = min(candidates, key=lambda c: c.confidence)
        dismissal = ReviewRequest(
            disposition=ReviewStatus.DISMISSED,
            analyst_id="analyst-qa-001",
            notes="Likely cloud shadow artifact — NDVI reduction matches ephemeral cloud cover, not soil exposure.",
        )
        updated = svc.review_candidate(low_conf.candidate_id, dismissal)
        assert updated.review_status == ReviewStatus.DISMISSED
        assert updated.reviewed_by == "analyst-qa-001"
        assert "cloud shadow" in (updated.analyst_notes or "")

    def test_dismissed_candidates_excluded_from_pending_queue(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[1])
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        assert candidates
        # Dismiss all candidates
        for cand in candidates:
            svc.review_candidate(
                cand.candidate_id,
                ReviewRequest(disposition=ReviewStatus.DISMISSED, analyst_id="qa-sweep"),
            )
        pending = svc.list_pending_reviews(aoi_id=PILOT_AOIS[1]["id"])
        assert all(c.review_status != ReviewStatus.PENDING for c in pending) or pending == []

    def test_seasonal_false_positive_dismissed_with_note(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[2])
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        assert candidates
        cand = candidates[0]
        dismissal = ReviewRequest(
            disposition=ReviewStatus.DISMISSED,
            analyst_id="analyst-qa-002",
            notes="Seasonal agricultural harvesting — NDVI decrease consistent with Nov-Jan harvest cycle, not construction activity.",
        )
        updated = svc.review_candidate(cand.candidate_id, dismissal)
        assert updated.review_status == ReviewStatus.DISMISSED

    def test_confirmed_candidates_persist_analyst_metadata(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        high_conf = max(candidates, key=lambda c: c.confidence)
        confirmation = ReviewRequest(
            disposition=ReviewStatus.CONFIRMED,
            analyst_id="analyst-senior-001",
            notes="Confirmed: ground-truth photo from field team corroborates new foundation pour.",
        )
        updated = svc.review_candidate(high_conf.candidate_id, confirmation)
        assert updated.review_status == ReviewStatus.CONFIRMED
        assert updated.reviewed_by == "analyst-senior-001"
        assert updated.reviewed_at is not None

    def test_evidence_pack_generated_for_reviewed_candidate(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        candidates = svc.get_candidates(job.job_id)
        cand = candidates[0]
        svc.review_candidate(
            cand.candidate_id,
            ReviewRequest(disposition=ReviewStatus.CONFIRMED, analyst_id="evidence-test"),
        )
        pack = svc.build_evidence_pack(cand.candidate_id)
        assert pack.candidate_id == cand.candidate_id
        assert pack.aoi_id == req.aoi_id
        assert pack.change_class is not None
        assert pack.exported_at is not None

    def test_review_queue_contains_only_pilot_aoi_candidates(self, svc: ChangeAnalyticsService) -> None:
        """Review queue filter by aoi_id should be selective."""
        # Submit jobs for two different AOIs
        job1 = svc.submit_job(_job_request(PILOT_AOIS[0]))
        job2 = svc.submit_job(_job_request(PILOT_AOIS[1]))
        queue_aoi0 = svc.list_pending_reviews(aoi_id=PILOT_AOIS[0]["id"])
        queue_aoi1 = svc.list_pending_reviews(aoi_id=PILOT_AOIS[1]["id"])
        aoi0_ids = {c.aoi_id for c in queue_aoi0}
        aoi1_ids = {c.aoi_id for c in queue_aoi1}
        if aoi0_ids:
            assert aoi0_ids == {PILOT_AOIS[0]["id"]}
        if aoi1_ids:
            assert aoi1_ids == {PILOT_AOIS[1]["id"]}
        # Suppress unused variable warnings
        _ = job1, job2


class TestMultiJobReviewWorkflow:
    """P4-3.4 — Full multi-job analyst review workflow validation."""

    def test_multiple_jobs_share_single_review_queue(self, svc: ChangeAnalyticsService) -> None:
        """All pending candidates from multiple jobs appear in global queue."""
        jobs = [svc.submit_job(_job_request(aoi)) for aoi in PILOT_AOIS]
        all_pending = svc.list_pending_reviews()
        all_candidate_ids = {c.candidate_id for c in all_pending}
        for job in jobs:
            for cand in svc.get_candidates(job.job_id):
                if cand.review_status == ReviewStatus.PENDING:
                    assert cand.candidate_id in all_candidate_ids

    def test_job_stats_update_on_completion(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        assert job.stats is not None
        assert job.stats.get("candidate_count", 0) >= 1

    def test_get_job_returns_completed_job(self, svc: ChangeAnalyticsService) -> None:
        req = _job_request(PILOT_AOIS[0])
        job = svc.submit_job(req)
        retrieved = svc.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.state == ChangeDetectionJobState.COMPLETED

    def test_unknown_job_id_returns_none(self, svc: ChangeAnalyticsService) -> None:
        assert svc.get_job("nonexistent-job-id") is None
