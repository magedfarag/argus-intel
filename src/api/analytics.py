"""Change Analytics router — P4-1 & P4-2.

Endpoints:
  POST /api/v1/analytics/change-detection
      Submit a batch change-detection job for an AOI.

  GET  /api/v1/analytics/change-detection/{job_id}
      Get job status and all detected candidates.

  GET  /api/v1/analytics/change-detection/{job_id}/candidates
      Get only the candidate list for a job.

  GET  /api/v1/analytics/review
      List change candidates pending analyst review (optionally filtered by AOI).

  PUT  /api/v1/analytics/change-detection/{candidate_id}/review
      Submit analyst disposition (confirmed / dismissed).

  POST /api/v1/analytics/correlation
      Correlate a candidate with nearby canonical events.

  GET  /api/v1/analytics/change-detection/{candidate_id}/evidence-pack
      Download an evidence pack for export / archiving.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.models.analytics import (
    ChangeCandidate,
    ChangeDetectionJobRequest,
    ChangeDetectionJobResponse,
    CorrelationRequest,
    CorrelationResponse,
    EvidencePack,
    ReviewRequest,
)
from src.services.change_analytics import ChangeAnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

# ── Module-level service singleton ────────────────────────────────────────────
_service = ChangeAnalyticsService()
_event_store: Optional[Any] = None


def get_analytics_service() -> ChangeAnalyticsService:
    """Return the module-level ChangeAnalyticsService (replaceable in tests)."""
    return _service


def set_analytics_service(svc: ChangeAnalyticsService) -> None:
    """Replace the service singleton. Used in tests."""
    global _service
    _service = svc


def set_analytics_event_store(store: Any) -> None:
    """Inject the shared EventStore for correlation + evidence-pack endpoints."""
    global _event_store
    _event_store = store


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/change-detection",
    response_model=ChangeDetectionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a change-detection batch job for an AOI (P4-1.2)",
)
def submit_change_detection(
    req: ChangeDetectionJobRequest,
) -> ChangeDetectionJobResponse:
    """Submit a change-detection batch job.

    The job runs synchronously (in-memory store). The Celery-dispatch-ready
    interface is preserved for production async promotion.
    """
    job = get_analytics_service().submit_job(req)
    return job


@router.get(
    "/change-detection/{job_id}",
    response_model=ChangeDetectionJobResponse,
    summary="Get job status + all detected candidates (P4-1.2)",
)
def get_change_detection_job(job_id: str) -> ChangeDetectionJobResponse:
    job = get_analytics_service().get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return job


@router.get(
    "/change-detection/{job_id}/candidates",
    response_model=List[ChangeCandidate],
    summary="Get change candidates for a job (P4-1.3)",
)
def get_job_candidates(job_id: str) -> List[ChangeCandidate]:
    svc = get_analytics_service()
    if svc.get_job(job_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return svc.get_candidates(job_id)


@router.get(
    "/review",
    response_model=List[ChangeCandidate],
    summary="List change candidates pending analyst review (P4-2.1)",
)
def list_pending_review(
    aoi_id: Optional[str] = Query(default=None, description="Filter by AOI ID."),
) -> List[ChangeCandidate]:
    return get_analytics_service().list_pending_reviews(aoi_id=aoi_id)


@router.put(
    "/change-detection/{candidate_id}/review",
    response_model=ChangeCandidate,
    summary="Submit analyst disposition for a change candidate (P4-2.2)",
)
def review_candidate(
    candidate_id: str,
    req: ReviewRequest,
) -> ChangeCandidate:
    updated = get_analytics_service().review_candidate(candidate_id, req)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found.",
        )
    return updated


@router.post(
    "/correlation",
    response_model=CorrelationResponse,
    summary="Correlate a change candidate with contextual events (P4-2.4)",
)
def correlate_candidate(req: CorrelationRequest) -> CorrelationResponse:
    result = get_analytics_service().correlate(req, event_store=_event_store)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{req.candidate_id}' not found.",
        )
    return result


@router.get(
    "/change-detection/{candidate_id}/evidence-pack",
    response_model=EvidencePack,
    summary="Export evidence pack for a change candidate (P4-2.5)",
)
def get_evidence_pack(candidate_id: str) -> EvidencePack:
    pack = get_analytics_service().build_evidence_pack(
        candidate_id, event_store=_event_store
    )
    if pack is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found.",
        )
    return pack
