"""GET /api/providers — list providers and their availability."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_registry
from app.models.responses import ProviderInfo, ProvidersResponse
from app.providers.registry import ProviderRegistry

router = APIRouter(prefix="/api", tags=["providers"])

_NOTES: dict = {
    "sentinel2": [
        "10 m resolution (visible + NIR bands)",
        "Revisit: ~5 days at the equator",
        "Free access via Copernicus Data Space Ecosystem (registration required)",
        "Cloud-free coverage not guaranteed within any 30-day window",
    ],
    "landsat": [
        "30 m resolution",
        "Revisit: ~16 days",
        "Free public access via USGS LandsatLook STAC (no credentials required for search)",
        "Suitable for large-area developments; may be too coarse for small urban sites",
    ],
    "maxar": [
        "0.3-0.5 m resolution (WorldView-3/4, GeoEye-1)",
        "Commercial subscription required (SecureWatch)",
        "Archive search via STAC-like API; tasked collection available",
        "Best for fine-grained urban construction monitoring",
    ],
    "planet": [
        "3-5 m resolution (PlanetScope); 0.5 m (SkySat)",
        "Commercial subscription required (Planet API key)",
        "Daily global revisit — ideal for change detection cadence",
        "Search via Planet Data API; COG streaming supported",
    ],
    "demo": [
        "Synthetic deterministic data — no real imagery",
        "Always available; used as fallback when live providers are unconfigured",
    ],
}


@router.get("/providers", response_model=ProvidersResponse, summary="Provider availability")
def list_providers(
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
) -> ProvidersResponse:
    infos = []
    for p in registry.all_providers():
        ok, reason = registry.get_availability(p.provider_name)
        infos.append(ProviderInfo(
            name=p.provider_name,
            display_name=p.display_name,
            available=ok,
            reason=None if ok else reason,
            resolution_m=p.resolution_m,
            notes=_NOTES.get(p.provider_name, []),
        ))
    demo_ok = registry.is_available("demo")
    return ProvidersResponse(providers=infos, demo_available=demo_ok)
