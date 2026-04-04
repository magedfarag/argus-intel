"""Thumbnail serving endpoint.

Serves pre-generated satellite scene thumbnails from the in-memory
cache.  Thumbnails are generated during the change detection pipeline
and cached in the :mod:`backend.app.services.thumbnails` module.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from app.services.thumbnails import get_cached_thumbnail

router = APIRouter(prefix="/api", tags=["thumbnails"])


@router.get("/thumbnails/{scene_id}")
async def get_thumbnail(
    scene_id: str,
    key: str = Query(..., description="Cache key returned by the analysis endpoint"),
) -> Response:
    """Return a cached scene thumbnail as PNG."""
    data = get_cached_thumbnail(key)
    if data is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Thumbnail not found for scene '{scene_id}'. "
                     "It may have expired or was never generated."},
        )
    return Response(content=data, media_type="image/png")
