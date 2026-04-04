"""GET /api/credits — usage counters."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.cache.client import CacheClient
from app.dependencies import get_cache
from app.models.responses import CreditsResponse

router = APIRouter(prefix="/api", tags=["usage"])


@router.get("/credits", response_model=CreditsResponse, summary="Usage summary")
def credits(
    cache: Annotated[CacheClient, Depends(get_cache)],
) -> CreditsResponse:
    stats = cache.stats()
    return CreditsResponse(
        provider_request_counts={},
        cache_hit_rate=stats["hit_rate"],
        cache_hits=stats["hits"],
        cache_misses=stats["misses"],
        estimated_scenes_fetched=0,
    )
