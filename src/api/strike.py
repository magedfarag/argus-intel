"""Strike reconstruction router — Phase 2, Track D.

GET  /api/v1/strikes                       — list strike events (filters: start,
                                             end, strike_type, confidence_min)
GET  /api/v1/strikes/summary               — aggregate counts by strike_type
                                             over 30-day window
GET  /api/v1/strikes/{strike_id}           — single event detail with evidence_refs
POST /api/v1/strikes/{strike_id}/evidence  — attach an EvidenceLink to a strike

Data is served from the ``StrikeLayerService`` singleton, which is seeded at
app startup and supports a live ACLED-connector swap (ARCH-01 / ARCH-02 / STR-02).
Routes no longer maintain module-level seeded stores.

IMPORTANT — route order: /summary is registered BEFORE /{strike_id} so that
GET /api/v1/strikes/summary is not captured by the path parameter route.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from pydantic import BaseModel

from app.dependencies import UserClaims, require_operator
from src.models.operational_layers import EvidenceLink, StrikeEvent
from src.services.operational_layer_service import _STUB_REF_NOW, get_strike_service

router = APIRouter(prefix="/api/v1/strikes", tags=["strikes"])

_WINDOW_DAYS = 30


# ── Response models ───────────────────────────────────────────────────────────


class StrikeListResponse(BaseModel):
    events: list[StrikeEvent]
    is_demo_data: bool = Field(
        default=False,
        description="True when backed by stub/demo data rather than a live ACLED source.",
    )


class StrikeSummaryResponse(BaseModel):
    counts: dict[str, int]
    is_demo_data: bool = Field(default=False)


# ── Endpoints — static routes FIRST to avoid param capture ───────────────────


@router.get(
    "",
    response_model=StrikeListResponse,
    summary="List strike events",
    description=(
        "Returns strike events from the service store. "
        "All query parameters are optional; omitting them returns all events."
    ),
)
def list_strikes(
    start=Query(
        default=None, description="Filter events on or after this UTC timestamp"
    ),
    end=Query(
        default=None, description="Filter events on or before this UTC timestamp"
    ),
    strike_type: str | None = Query(
        default=None,
        description="Filter by strike type: airstrike | artillery | missile | drone | unknown",
    ),
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> StrikeListResponse:
    svc = get_strike_service()
    results = list(svc.all_strikes().values())

    if start is not None:
        results = [e for e in results if e.occurred_at >= start]
    if end is not None:
        results = [e for e in results if e.occurred_at <= end]
    if strike_type is not None:
        results = [e for e in results if e.strike_type == strike_type]
    if confidence_min > 0.0:
        results = [e for e in results if e.confidence >= confidence_min]

    results.sort(key=lambda e: e.occurred_at, reverse=True)
    return StrikeListResponse(events=results, is_demo_data=svc.is_demo_mode)


@router.get(
    "/summary",
    response_model=StrikeSummaryResponse,
    summary="Strike counts by type over the last 30 days",
    description=(
        "Returns a dict mapping each strike_type to the count of events "
        "occurring within the last 30 days (relative to the reference date)."
    ),
)
def get_strikes_summary() -> StrikeSummaryResponse:
    svc = get_strike_service()
    window_start = _STUB_REF_NOW - timedelta(days=_WINDOW_DAYS)
    counts: dict[str, int] = {}
    for ev in svc.all_strikes().values():
        if ev.occurred_at >= window_start:
            counts[ev.strike_type] = counts.get(ev.strike_type, 0) + 1
    return StrikeSummaryResponse(counts=counts, is_demo_data=svc.is_demo_mode)


@router.post(
    "/{strike_id}/evidence",
    response_model=StrikeEvent,
    summary="Attach an evidence link to a strike event",
    description=(
        "Appends an EvidenceLink to the strike's evidence store and increments "
        "corroboration_count.  Idempotent: duplicate evidence_ids are ignored."
    ),
)
def attach_evidence(
    strike_id: str,
    link: EvidenceLink,
    _user: UserClaims = Depends(require_operator),
) -> StrikeEvent:
    svc = get_strike_service()
    ev = svc.get_strike(strike_id)
    if ev is None:
        raise HTTPException(
            status_code=404, detail=f"Strike {strike_id!r} not found"
        )

    # Idempotent by evidence_id
    existing = {el.evidence_id for el in svc.list_evidence(strike_id)}
    if link.evidence_id not in existing:
        svc.attach_evidence(strike_id, link)
        # Delegate evidence-ref merge to the connector helper
        from src.connectors.strike_connector import StrikeConnector
        _stub_connector = StrikeConnector()
        updated = _stub_connector.add_evidence(ev, [link])
        # Persist the updated strike in the service store
        from threading import Lock  # noqa: F401
        svc._store[strike_id] = updated  # direct update — service owns the store
        return updated

    return ev


@router.get(
    "/{strike_id}",
    response_model=StrikeEvent,
    summary="Retrieve a single strike event by ID",
    description="Returns the strike event including all evidence_refs attached so far.",
)
def get_strike(strike_id: str) -> StrikeEvent:
    ev = get_strike_service().get_strike(strike_id)
    if ev is None:
        raise HTTPException(
            status_code=404, detail=f"Strike {strike_id!r} not found"
        )
    return ev

