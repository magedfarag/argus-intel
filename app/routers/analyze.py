"""POST /api/analyze — synchronous and asynchronous analysis."""
from __future__ import annotations

import math
from typing import Annotated, Union

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.cache.client import CacheClient
from app.config import AppSettings
from app.dependencies import get_app_settings, get_cache, get_circuit_breaker, get_job_manager, get_registry, verify_api_key
from app.models.requests import AnalyzeRequest
from app.models.responses import AnalyzeResponse, JobStatusResponse
from app.providers.base import ProviderUnavailableError
from app.providers.demo import MAX_AREA_KM2, MIN_AREA_KM2, _polygon_area_km2
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.rate_limiter import ANALYZE_RATE_LIMIT, limiter
from app.services.analysis import AnalysisService
from app.services.job_manager import JobManager

router = APIRouter(prefix="/api", tags=["analysis"])


def _get_analysis_service(
    settings: AppSettings,
    registry: ProviderRegistry,
    cache: CacheClient,
    breaker: CircuitBreaker,
    job_manager: Union[JobManager, None] = None,
) -> AnalysisService:
    """Construct AnalysisService with optional JobManager (singleton from DI)."""
    return AnalysisService(registry=registry, cache=cache, settings=settings, job_manager=job_manager, breaker=breaker)


def _validate_area(request: AnalyzeRequest) -> float:
    """Validate geometry and return computed area_km2."""
    from app.services.analysis import _flatten_coords
    try:
        coords = _flatten_coords(request.geometry.model_dump())
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        area = _polygon_area_km2(coords)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if area < MIN_AREA_KM2 or area > MAX_AREA_KM2:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Area must be between {MIN_AREA_KM2} km² and {MAX_AREA_KM2} km². "
                f"Computed: {area:.4f} km²"
            ),
        )
    return area


@router.post(
    "/analyze",
    response_model=Union[AnalyzeResponse, JobStatusResponse],
    summary="Analyse AOI for construction activity",
    responses={
        200: {"description": "Synchronous analysis result or async job ticket"},
        400: {"description": "Invalid geometry or date range"},
        503: {"description": "No providers available"},
    },
)
@limiter.limit(ANALYZE_RATE_LIMIT)
def analyze(
    body: AnalyzeRequest,
    request: Request,
    settings: Annotated[AppSettings,      Depends(get_app_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
    cache:    Annotated[CacheClient,      Depends(get_cache)],
    breaker:  Annotated[CircuitBreaker,   Depends(get_circuit_breaker)],
    job_manager: Annotated[Union[JobManager, None], Depends(get_job_manager)],
    _: Annotated[str, Depends(verify_api_key)],  # Required API key authentication
) -> Union[AnalyzeResponse, JobStatusResponse]:
    area = _validate_area(body)
    use_async = body.async_execution or area > settings.async_area_threshold_km2

    svc = _get_analysis_service(settings, registry, cache, breaker, job_manager)

    try:
        if use_async and settings.effective_celery_broker():
            job_id = svc.submit_async(body)
            return JobStatusResponse(
                job_id=job_id,
                state="pending",
                created_at="",
                updated_at="",
            )
        return svc.run_sync(body)
    except ProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc!s}",
        ) from exc
