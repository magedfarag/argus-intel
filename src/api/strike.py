"""Strike reconstruction router — Phase 2, Track D.

GET  /api/v1/strikes                       — list strike events (filters: start,
                                             end, strike_type, confidence_min)
GET  /api/v1/strikes/summary               — aggregate counts by strike_type
                                             over 30-day window
GET  /api/v1/strikes/{strike_id}           — single event detail with evidence_refs
POST /api/v1/strikes/{strike_id}/evidence  — attach an EvidenceLink to a strike

In-memory store is seeded at module load with 5 deterministic events spanning
the 30 days prior to the project reference date (2026-04-04).

IMPORTANT — route order: /summary is registered BEFORE /{strike_id} so that
GET /api/v1/strikes/summary is not captured by the path parameter route.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import UserClaims, require_operator

from src.connectors.strike_connector import StrikeConnector
from src.models.operational_layers import EvidenceLink, StrikeEvent

router = APIRouter(prefix="/api/v1/strikes", tags=["strikes"])

# ── In-memory stores ──────────────────────────────────────────────────────────
_connector = StrikeConnector()
_store: Dict[str, StrikeEvent] = {}
# Per-strike list of attached evidence links
_evidence_store: Dict[str, List[EvidenceLink]] = {}

# Fixed reference "now" for deterministic seeding (project-relative timestamp)
_REF_NOW = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)
_WINDOW_DAYS = 30


def _seed_store() -> None:
    """Seed the in-memory store with 5 deterministic strike events.

    Draws from two consecutive 30-day windows to guarantee at least 5 events
    regardless of how many the connector returns from a single window.
    """
    w1_end = _REF_NOW
    w1_start = _REF_NOW - timedelta(days=_WINDOW_DAYS)
    events: List[StrikeEvent] = _connector.fetch_strikes(w1_start, w1_end)

    if len(events) < 5:
        w2_end = w1_start
        w2_start = _REF_NOW - timedelta(days=60)
        events.extend(_connector.fetch_strikes(w2_start, w2_end))

    for ev in events[:5]:
        _store[ev.strike_id] = ev
        _evidence_store[ev.strike_id] = []


_seed_store()


# ── Endpoints — static routes FIRST to avoid param capture ───────────────────


@router.get(
    "",
    response_model=List[StrikeEvent],
    summary="List strike events",
    description=(
        "Returns strike events from the in-memory store.  "
        "All query parameters are optional; omitting them returns all events."
    ),
)
def list_strikes(
    start: Optional[datetime] = Query(
        default=None, description="Filter events on or after this UTC timestamp"
    ),
    end: Optional[datetime] = Query(
        default=None, description="Filter events on or before this UTC timestamp"
    ),
    strike_type: Optional[str] = Query(
        default=None,
        description="Filter by strike type: airstrike | artillery | missile | drone | unknown",
    ),
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> List[StrikeEvent]:
    results = list(_store.values())

    if start is not None:
        results = [e for e in results if e.occurred_at >= start]
    if end is not None:
        results = [e for e in results if e.occurred_at <= end]
    if strike_type is not None:
        results = [e for e in results if e.strike_type == strike_type]
    if confidence_min > 0.0:
        results = [e for e in results if e.confidence >= confidence_min]

    results.sort(key=lambda e: e.occurred_at, reverse=True)
    return results


@router.get(
    "/summary",
    response_model=Dict[str, int],
    summary="Strike counts by type over the last 30 days",
    description=(
        "Returns a dict mapping each strike_type to the count of events "
        "occurring within the last 30 days (relative to the reference date)."
    ),
)
def get_strikes_summary() -> Dict[str, int]:
    window_start = _REF_NOW - timedelta(days=_WINDOW_DAYS)
    counts: Dict[str, int] = {}
    for ev in _store.values():
        if ev.occurred_at >= window_start:
            counts[ev.strike_type] = counts.get(ev.strike_type, 0) + 1
    return counts


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
    ev = _store.get(strike_id)
    if ev is None:
        raise HTTPException(
            status_code=404, detail=f"Strike {strike_id!r} not found"
        )

    # Append to per-strike evidence list (idempotent by evidence_id)
    existing_ids = {el.evidence_id for el in _evidence_store.get(strike_id, [])}
    if link.evidence_id not in existing_ids:
        _evidence_store.setdefault(strike_id, []).append(link)
        updated = _connector.add_evidence(ev, [link])
        _store[strike_id] = updated
        return updated

    return ev


@router.get(
    "/{strike_id}",
    response_model=StrikeEvent,
    summary="Retrieve a single strike event by ID",
    description="Returns the strike event including all evidence_refs attached so far.",
)
def get_strike(strike_id: str) -> StrikeEvent:
    ev = _store.get(strike_id)
    if ev is None:
        raise HTTPException(
            status_code=404, detail=f"Strike {strike_id!r} not found"
        )
    return ev
