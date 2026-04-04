"""Analyst query and briefing router — Phase 5 Track C.

Endpoints:
  POST   /api/v1/analyst/query                           execute ad-hoc query (ephemeral)
  POST   /api/v1/analyst/queries                         save query for reuse
  GET    /api/v1/analyst/queries                         list saved queries
  GET    /api/v1/analyst/queries/{query_id}              get saved query
  DELETE /api/v1/analyst/queries/{query_id}              delete saved query (204)
  POST   /api/v1/analyst/queries/{query_id}/execute      execute a saved query
  POST   /api/v1/analyst/briefings                       generate new briefing
  GET    /api/v1/analyst/briefings                       list briefings
  GET    /api/v1/analyst/briefings/{briefing_id}         get briefing
  GET    /api/v1/analyst/briefings/{briefing_id}/text    download text report
  POST   /api/v1/analyst/briefings/from-investigation/{inv_id}  briefing from investigation
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.cache.query_cache import get_query_cache
from app.cost_guardrails import require_briefing_quota
from app.dependencies import UserClaims, require_analyst, require_operator
from app.rate_limiter import heavy_endpoint_rate_limit

from src.models.analyst_query import (
    AnalystQuery,
    BriefingOutput,
    BriefingRequest,
    BriefingSection,
    QueryResult,
)
from src.services.analyst_query_service import get_default_analyst_query_service
from src.services.investigation_service import get_default_investigation_store

router = APIRouter(prefix="/api/v1/analyst", tags=["analyst"])


def _svc():
    return get_default_analyst_query_service()


def _get_query_or_404(query_id: str) -> AnalystQuery:
    q = _svc().get_saved_query(query_id)
    if q is None:
        raise HTTPException(status_code=404, detail=f"Query {query_id!r} not found")
    return q


def _get_briefing_or_404(briefing_id: str) -> BriefingOutput:
    b = _svc().get_briefing(briefing_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Briefing {briefing_id!r} not found")
    return b


# ── Sub-resource endpoints (MUST be before /{query_id} / /{briefing_id}) ─────


@router.post(
    "/briefings/from-investigation/{inv_id}",
    response_model=BriefingOutput,
    status_code=201,
    summary="Generate briefing from investigation",
)
def generate_briefing_from_investigation(
    inv_id: str,
    classification_label: str = Query(default="UNCLASSIFIED"),
    created_by: Optional[str] = Query(default=None),
    _quota: UserClaims = Depends(require_briefing_quota),
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> BriefingOutput:
    inv = get_default_investigation_store().get(inv_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"Investigation {inv_id!r} not found")
    req = BriefingRequest(
        title=f"Briefing: {inv.name}",
        investigation_id=inv_id,
        classification_label=classification_label,
        created_by=created_by,
        sections=list(BriefingSection),
    )
    return _svc().generate_briefing(req)


@router.post(
    "/queries/{query_id}/execute",
    response_model=QueryResult,
    summary="Execute a saved query",
)
def execute_saved_query(query_id: str) -> QueryResult:
    q = _get_query_or_404(query_id)
    return _svc().execute_query(q)


# ── Query surface ─────────────────────────────────────────────────────────────


@router.post(
    "/query",
    response_model=QueryResult,
    summary="Execute an ad-hoc query (not saved)",
)
def execute_adhoc_query(query: AnalystQuery) -> QueryResult:
    return _svc().execute_query(query)


@router.post(
    "/queries",
    response_model=AnalystQuery,
    status_code=201,
    summary="Save a query for reuse",
)
def save_query(
    query: AnalystQuery,
    _user: UserClaims = Depends(require_operator),
) -> AnalystQuery:
    return _svc().save_query(query)


@router.get(
    "/queries",
    response_model=List[AnalystQuery],
    summary="List saved queries",
)
def list_queries() -> List[AnalystQuery]:
    return _svc().list_saved_queries()


@router.get(
    "/queries/{query_id}",
    response_model=AnalystQuery,
    summary="Get saved query by ID",
)
def get_query(query_id: str) -> AnalystQuery:
    return _get_query_or_404(query_id)


@router.delete(
    "/queries/{query_id}",
    status_code=204,
    summary="Delete saved query",
)
def delete_query(query_id: str) -> Response:
    deleted = _svc().delete_saved_query(query_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Query {query_id!r} not found")
    return Response(status_code=204)


# ── Briefing surface ──────────────────────────────────────────────────────────


@router.post(
    "/briefings",
    response_model=BriefingOutput,
    status_code=201,
    summary="Generate a new analyst briefing",
)
def generate_briefing(
    req: BriefingRequest,
    _user: UserClaims = Depends(require_operator),
    _quota: UserClaims = Depends(require_briefing_quota),
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> BriefingOutput:
    return _svc().generate_briefing(req)


@router.get(
    "/briefings",
    response_model=List[BriefingOutput],
    summary="List briefings",
)
def list_briefings(
    investigation_id: Optional[str] = Query(default=None),
) -> List[BriefingOutput]:
    cache_key = f"analyst:briefings:list:{investigation_id}"
    qc = get_query_cache()
    cached = qc.get(cache_key)
    if cached is not None:
        return cached
    result = _svc().list_briefings(investigation_id=investigation_id)
    qc.set(cache_key, result, ttl=60.0)
    return result


@router.get(
    "/briefings/{briefing_id}",
    response_model=BriefingOutput,
    summary="Get a briefing by ID",
)
def get_briefing(briefing_id: str) -> BriefingOutput:
    return _get_briefing_or_404(briefing_id)


@router.get(
    "/briefings/{briefing_id}/text",
    response_class=Response,
    summary="Download briefing as plain text report",
)
def get_briefing_text(briefing_id: str) -> Response:
    briefing = _get_briefing_or_404(briefing_id)
    text = _svc().export_briefing_text(briefing)
    return Response(content=text, media_type="text/plain")
