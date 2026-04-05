"""AOI CRUD router — POST /api/v1/aois … DELETE /api/v1/aois/:id.

P1-2: Analyst-defined areas of interest are the primary scope unit for
every downstream search, replay, and export operation.

Backing store is in-memory (src/services/aoi_store.py) until the PostGIS
migration (P0-4) is complete.  The router is independent of the backend.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.aoi import AOICreate, AOIListResponse, AOIResponse, AOIUpdate
from src.services.aoi_store import AOIStore

router = APIRouter(prefix="/api/v1/aois", tags=["aois"])

# ── Dependency ────────────────────────────────────────────────────────────────
# A singleton store is injected via the module-level instance.
# Replace with a proper Depends(get_db) once PostGIS is wired.

_store = AOIStore()


def get_aoi_store() -> AOIStore:
    return _store


StoreDep = Annotated[AOIStore, Depends(get_aoi_store)]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=AOIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AOI",
)
def create_aoi(payload: AOICreate, store: StoreDep) -> AOIResponse:
    """Save an analyst-defined area of interest.

    The geometry must be a GeoJSON Polygon or MultiPolygon in EPSG:4326.
    Client-side circles must be converted to step-polygons before posting.
    """
    return store.create(payload)


@router.get(
    "",
    response_model=AOIListResponse,
    summary="List all active AOIs (paginated)",
)
def list_aois(
    store: StoreDep,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
) -> AOIListResponse:
    items = store.list_active(page=page, page_size=page_size)
    total = store.count_active()
    return AOIListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


@router.get(
    "/{aoi_id}",
    response_model=AOIResponse,
    summary="Get a single AOI by ID",
)
def get_aoi(aoi_id: str, store: StoreDep) -> AOIResponse:
    aoi = store.get(aoi_id)
    if not aoi:
        raise HTTPException(status_code=404, detail=f"AOI not found: {aoi_id}")
    return aoi


@router.put(
    "/{aoi_id}",
    response_model=AOIResponse,
    summary="Update AOI geometry or name",
)
def update_aoi(aoi_id: str, patch: AOIUpdate, store: StoreDep) -> AOIResponse:
    updated = store.update(aoi_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail=f"AOI not found: {aoi_id}")
    return updated


@router.delete(
    "/{aoi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Soft-delete an AOI",
)
def delete_aoi(aoi_id: str, store: StoreDep) -> None:
    """Soft-delete: marks the AOI as deleted but preserves history and event linkages."""
    if not store.soft_delete(aoi_id):
        raise HTTPException(status_code=404, detail=f"AOI not found: {aoi_id}")
