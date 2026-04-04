"""GET /api/jobs/{job_id} — async job status and results."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import AppSettings
from app.dependencies import get_app_settings, verify_api_key
from app.models.responses import AnalyzeResponse, JobStatusResponse
from app.resilience.rate_limiter import JOBS_RATE_LIMIT, limiter

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Async job status",
)
@limiter.limit(JOBS_RATE_LIMIT)
def get_job_status(
    request: Request,
    job_id: str,
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> JobStatusResponse:
    # Use Celery AsyncResult as the source of truth
    if not settings.effective_celery_broker():
        raise HTTPException(
            status_code=503,
            detail="Async jobs require Redis / Celery (see REDIS_URL in .env.example)",
        )
    try:
        from celery.result import AsyncResult
        from app.workers.celery_app import celery_app

        res = AsyncResult(job_id, app=celery_app)
        state = res.state.lower()

        result: AnalyzeResponse | None = None
        error: str | None = None

        if state == "success":
            state = "completed"
            raw = res.result
            if isinstance(raw, dict):
                result = AnalyzeResponse(**raw)
        elif state == "failure":
            state = "failed"
            error = str(res.result)

        return JobStatusResponse(
            job_id=job_id,
            state=state,
            result=result,
            error=error,
            created_at="",
            updated_at="",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Job lookup failed: {exc!s}") from exc


@router.delete(
    "/jobs/{job_id}/cancel",
    summary="Cancel a pending/running job",
    status_code=202,
)
def cancel_job(
    job_id: str,
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    _: Annotated[str, Depends(verify_api_key)],  # Required API key authentication
) -> dict:
    if not settings.effective_celery_broker():
        raise HTTPException(status_code=503, detail="Celery not configured")
    try:
        from app.workers.celery_app import celery_app
        celery_app.control.revoke(job_id, terminate=True)
        return {"job_id": job_id, "status": "cancellation_requested"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
