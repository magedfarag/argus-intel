"""Evidence packs router — Phase 5 Track B.

Endpoints:
  GET    /api/v1/evidence-packs                       list packs (?investigation_id=)
  POST   /api/v1/evidence-packs                       generate new pack
  GET    /api/v1/evidence-packs/{pack_id}             get pack
  DELETE /api/v1/evidence-packs/{pack_id}             delete (204)
  GET    /api/v1/evidence-packs/{pack_id}/download    download rendered pack (?format=json|markdown|geojson)
  POST   /api/v1/evidence-packs/from-investigation/{inv_id}  generate from investigation
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.cache.query_cache import get_query_cache
from app.cost_guardrails import require_evidence_pack_quota
from app.dependencies import UserClaims
from app.rate_limiter import heavy_endpoint_rate_limit
from src.models.evidence_pack import (
    EvidencePack,
    EvidencePackFormat,
    EvidencePackRequest,
)
from src.services.evidence_pack_service import get_default_evidence_pack_service
from src.services.investigation_service import get_default_investigation_store

router = APIRouter(prefix="/api/v1/evidence-packs", tags=["evidence-packs"])

_CONTENT_TYPES: dict[EvidencePackFormat, str] = {
    EvidencePackFormat.JSON: "application/json",
    EvidencePackFormat.MARKDOWN: "text/markdown",
    EvidencePackFormat.GEOJSON: "application/geo+json",
}


def _svc():
    return get_default_evidence_pack_service()


def _get_or_404(pack_id: str) -> EvidencePack:
    pack = _svc().get_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Evidence pack {pack_id!r} not found")
    return pack


# ── Sub-resource endpoints (MUST be before /{pack_id}) ───────────────────────


@router.post(
    "/from-investigation/{inv_id}",
    response_model=EvidencePack,
    status_code=201,
    summary="Generate evidence pack from investigation",
)
def generate_from_investigation(
    inv_id: str,
    title: Optional[str] = Query(default=None, description="Override pack title"),
    export_format: EvidencePackFormat = Query(
        default=EvidencePackFormat.JSON, description="Desired output format"
    ),
    _quota: UserClaims = Depends(require_evidence_pack_quota),
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> EvidencePack:
    inv = get_default_investigation_store().get(inv_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"Investigation {inv_id!r} not found")

    req = EvidencePackRequest(
        title=title or f"Evidence Pack: {inv.name}",
        description=inv.description,
        investigation_id=inv_id,
        event_ids=list(inv.linked_event_ids) if inv.linked_event_ids else None,
        export_format=export_format,
    )
    return _svc().generate_pack(req)


# ── Collection endpoints ──────────────────────────────────────────────────────


@router.get("", response_model=List[EvidencePack], summary="List evidence packs")
def list_packs(
    investigation_id: Optional[str] = Query(
        default=None, description="Filter by linked investigation ID"
    ),
) -> List[EvidencePack]:
    cache_key = f"evidence-packs:list:{investigation_id}"
    qc = get_query_cache()
    cached = qc.get(cache_key)
    if cached is not None:
        return cached
    result = _svc().list_packs(investigation_id=investigation_id)
    qc.set(cache_key, result, ttl=60.0)
    return result


@router.post("", response_model=EvidencePack, status_code=201, summary="Generate evidence pack")
def generate_pack(
    req: EvidencePackRequest,
    _quota: UserClaims = Depends(require_evidence_pack_quota),
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> EvidencePack:
    return _svc().generate_pack(req)


# ── Item endpoints ────────────────────────────────────────────────────────────


@router.get("/{pack_id}", response_model=EvidencePack, summary="Get evidence pack")
def get_pack(pack_id: str) -> EvidencePack:
    cache_key = f"evidence-packs:{pack_id}"
    qc = get_query_cache()
    cached = qc.get(cache_key)
    if cached is not None:
        return cached
    result = _get_or_404(pack_id)
    qc.set(cache_key, result, ttl=60.0)
    return result


@router.delete("/{pack_id}", status_code=204, summary="Delete evidence pack")
def delete_pack(pack_id: str) -> Response:
    _get_or_404(pack_id)
    _svc().delete_pack(pack_id)
    return Response(status_code=204)


@router.get("/{pack_id}/download", summary="Download rendered evidence pack")
def download_pack(
    pack_id: str,
    format: EvidencePackFormat = Query(
        default=EvidencePackFormat.JSON,
        description="Output format: json, markdown, or geojson",
    ),
) -> Response:
    pack = _get_or_404(pack_id)
    content = _svc().render_pack(pack, format)
    content_type = _CONTENT_TYPES.get(format, "application/octet-stream")
    filename = f"evidence_pack_{pack_id}.{format.value}"
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
