"""GET /api/config — application configuration state."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.cache.client import CacheClient
from app.config import AppSettings
from app.dependencies import get_app_settings, get_cache
from app.models.responses import ConfigResponse
from app.providers.demo import TODAY, MAX_LOOKBACK, MIN_AREA_KM2, MAX_AREA_KM2

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/config", response_model=ConfigResponse, summary="Client configuration")
def config(
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    cache:    Annotated[CacheClient, Depends(get_cache)],
) -> ConfigResponse:
    return ConfigResponse(
        today=TODAY.isoformat(),
        min_area_km2=MIN_AREA_KM2,
        max_area_km2=MAX_AREA_KM2,
        max_lookback_days=MAX_LOOKBACK,
        supported_providers=["demo", "auto", "sentinel2", "landsat", "maxar", "planet"],
        app_mode=settings.app_mode,
        async_area_threshold_km2=settings.async_area_threshold_km2,
        default_cloud_threshold=settings.default_cloud_threshold,
        cache_ttl_seconds=settings.cache_ttl_seconds,
        redis_available=settings.redis_available(),
        celery_available=bool(settings.effective_celery_broker()),
    )
