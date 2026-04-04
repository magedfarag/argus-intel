"""Investigations router — Phase 5 Track A.

Endpoints:
  GET    /api/v1/investigations              list (optional ?status= filter)
  POST   /api/v1/investigations              create
  GET    /api/v1/investigations/{id}         get single
  PUT    /api/v1/investigations/{id}         update
  DELETE /api/v1/investigations/{id}         delete (204)
  POST   /api/v1/investigations/{id}/notes   add note
  POST   /api/v1/investigations/{id}/watchlist  add watchlist entry
  POST   /api/v1/investigations/{id}/evidence   add evidence link (idempotent)
  POST   /api/v1/investigations/{id}/filters    save filter
  GET    /api/v1/investigations/{id}/export     export as JSON
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.dependencies import UserClaims, require_analyst, require_operator

from src.models.investigations import (
    Investigation,
    InvestigationCreateRequest,
    InvestigationListResponse,
    InvestigationNote,
    InvestigationStatus,
    InvestigationUpdateRequest,
    SavedFilter,
    WatchlistEntry,
)
from src.models.operational_layers import EvidenceLink
from src.services.investigation_service import get_default_investigation_store

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


def _store():
    return get_default_investigation_store()


def _get_or_404(investigation_id: str) -> Investigation:
    inv = _store().get(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id!r} not found")
    return inv


# ── Collection endpoints ──────────────────────────────────────────────────────


@router.get("", response_model=InvestigationListResponse, summary="List investigations")
def list_investigations(
    status: Optional[InvestigationStatus] = Query(
        default=None, description="Filter by investigation status"
    ),
    _user: UserClaims = Depends(require_analyst),
) -> InvestigationListResponse:
    items = _store().list_all(status=status)
    return InvestigationListResponse(items=items, total=len(items))


@router.post("", response_model=Investigation, status_code=201, summary="Create investigation")
def create_investigation(
    req: InvestigationCreateRequest,
    _user: UserClaims = Depends(require_operator),
) -> Investigation:
    return _store().create(req)


# ── Sub-resource endpoints (MUST be registered before /{investigation_id}) ────

# (none needed — all are under /{id}/...)


# ── Item endpoints ────────────────────────────────────────────────────────────


@router.get("/{investigation_id}", response_model=Investigation, summary="Get investigation")
def get_investigation(
    investigation_id: str,
    _user: UserClaims = Depends(require_analyst),
) -> Investigation:
    return _get_or_404(investigation_id)


@router.put("/{investigation_id}", response_model=Investigation, summary="Update investigation")
def update_investigation(
    investigation_id: str, req: InvestigationUpdateRequest,
    _user: UserClaims = Depends(require_operator),
) -> Investigation:
    _get_or_404(investigation_id)  # raise 404 early if missing
    updated = _store().update(investigation_id, req)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id!r} not found")
    return updated


@router.delete("/{investigation_id}", status_code=204, summary="Delete investigation")
def delete_investigation(
    investigation_id: str,
    _user: UserClaims = Depends(require_operator),
) -> Response:
    _get_or_404(investigation_id)
    _store().delete(investigation_id)
    return Response(status_code=204)


# ── Sub-resource mutation endpoints ──────────────────────────────────────────


@router.post(
    "/{investigation_id}/notes",
    response_model=Investigation,
    status_code=201,
    summary="Add note",
)
def add_note(
    investigation_id: str,
    note: InvestigationNote,
    _user: UserClaims = Depends(require_operator),
) -> Investigation:
    _get_or_404(investigation_id)
    updated = _store().add_note(investigation_id, note)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id!r} not found")
    return updated


@router.post(
    "/{investigation_id}/watchlist",
    response_model=Investigation,
    status_code=201,
    summary="Add watchlist entry",
)
def add_watchlist_entry(
    investigation_id: str,
    entry: WatchlistEntry,
    _user: UserClaims = Depends(require_operator),
) -> Investigation:
    _get_or_404(investigation_id)
    updated = _store().add_watchlist_entry(investigation_id, entry)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id!r} not found")
    return updated


@router.post(
    "/{investigation_id}/evidence",
    response_model=Investigation,
    status_code=201,
    summary="Add evidence link (idempotent)",
)
def add_evidence_link(
    investigation_id: str,
    link: EvidenceLink,
    _user: UserClaims = Depends(require_operator),
) -> Investigation:
    _get_or_404(investigation_id)
    updated = _store().add_evidence_link(investigation_id, link)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id!r} not found")
    return updated


@router.post(
    "/{investigation_id}/filters",
    response_model=Investigation,
    status_code=201,
    summary="Save filter",
)
def add_saved_filter(
    investigation_id: str,
    filt: SavedFilter,
    _user: UserClaims = Depends(require_operator),
) -> Investigation:
    _get_or_404(investigation_id)
    updated = _store().add_saved_filter(investigation_id, filt)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id!r} not found")
    return updated


# ── Export endpoint ───────────────────────────────────────────────────────────


@router.get(
    "/{investigation_id}/export",
    response_model=Investigation,
    summary="Export investigation as JSON",
    description="Returns the full Investigation object as JSON for sharing or archival.",
)
def export_investigation(
    investigation_id: str,
    _user: UserClaims = Depends(require_analyst),
) -> Investigation:
    return _get_or_404(investigation_id)
