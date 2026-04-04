"""Cache statistics endpoint — Phase 6 Track B.

Route:
  GET /api/v1/cache/stats  — hit rate, miss rate, eviction count, total entries
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from app.cache.query_cache import get_query_cache

router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


@router.get(
    "/stats",
    summary="Query cache statistics",
    response_model=None,
)
def get_cache_stats() -> Dict[str, Any]:
    """Return hit/miss rates, eviction count, and live entry count for the
    in-process query cache.
    """
    return get_query_cache().stats()
