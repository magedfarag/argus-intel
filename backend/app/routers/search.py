"""POST /api/search — search imagery without running analysis."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_registry, verify_api_key
from backend.app.models.requests import SearchRequest
from backend.app.models.responses import SceneSearchResult, SearchResponse
from backend.app.providers.registry import ProviderRegistry

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse, summary="Search satellite imagery")
def search_imagery(
    request: SearchRequest,
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
    _: Annotated[str, Depends(verify_api_key)],  # Required API key authentication
) -> SearchResponse:
    provider = registry.select_provider(request.provider)
    warnings = []

    if provider is None or provider.provider_name == "demo":
        warnings.append("No live provider available; demo search returns synthetic metadata.")
        from backend.app.providers.demo import DemoProvider
        provider = DemoProvider()

    try:
        scenes = provider.search_imagery(
            geometry=request.geometry.model_dump(),
            start_date=request.start_date.isoformat(),
            end_date=request.end_date.isoformat(),
            cloud_threshold=request.cloud_threshold,
            max_results=request.max_results,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Provider search failed: {exc!s}") from exc

    results = [
        SceneSearchResult(
            scene_id=s.scene_id,
            provider=s.provider,
            satellite=s.satellite,
            acquired_at=s.acquired_at.isoformat(),
            cloud_cover=s.cloud_cover,
            bbox=s.bbox,
            resolution_m=s.resolution_m,
            asset_urls=s.assets,
        )
        for s in scenes
    ]
    return SearchResponse(
        scenes=results,
        total=len(results),
        provider=provider.provider_name,
        warnings=warnings,
    )
