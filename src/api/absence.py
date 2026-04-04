"""Absence-As-Signal API router — Phase 5 Track D.

Endpoints:
  GET  /api/v1/absence/signals                     list signals (filters: signal_type, entity_id, active_only, min_confidence)
  POST /api/v1/absence/signals                     create signal manually (201)
  GET  /api/v1/absence/signals/{signal_id}         get single signal
  POST /api/v1/absence/signals/{signal_id}/resolve resolve with gap_end timestamp
  POST /api/v1/absence/signals/{signal_id}/link-event  link to canonical event

  GET  /api/v1/absence/alerts                      list current alerts (min_severity filter)
  GET  /api/v1/absence/summary                     analytics summary for a time window
  POST /api/v1/absence/scan/ais-gaps               trigger AIS gap detection scan
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.cache.query_cache import get_query_cache
from app.dependencies import UserClaims, require_analyst, require_operator
from app.rate_limiter import heavy_endpoint_rate_limit

from src.models.absence_signals import (
    AbsenceAlert,
    AbsenceAnalyticsSummary,
    AbsenceSeverity,
    AbsenceSignal,
    AbsenceSignalCreateRequest,
    AbsenceSignalType,
)
from src.services.absence_analytics import get_default_absence_service

router = APIRouter(prefix="/api/v1/absence", tags=["absence"])


def _svc():
    return get_default_absence_service()


def _get_signal_or_404(signal_id: str) -> AbsenceSignal:
    signal = _svc().get_signal(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id!r} not found")
    return signal


# ── Signal collection ─────────────────────────────────────────────────────────


@router.get(
    "/signals",
    response_model=List[AbsenceSignal],
    summary="List absence signals",
)
def list_signals(
    signal_type: Optional[AbsenceSignalType] = Query(
        default=None, description="Filter by signal type"
    ),
    entity_id: Optional[str] = Query(
        default=None, description="Filter by entity ID"
    ),
    active_only: bool = Query(
        default=False, description="Return only signals with no gap_end (ongoing)"
    ),
    min_confidence: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
) -> List[AbsenceSignal]:
    cache_key = (
        f"absence:signals:{signal_type}:{entity_id}"
        f":{active_only}:{min_confidence}:{limit}"
    )
    qc = get_query_cache()
    cached = qc.get(cache_key)
    if cached is not None:
        return cached
    result = _svc().list_signals(
        signal_type=signal_type,
        entity_id=entity_id,
        active_only=active_only,
        min_confidence=min_confidence,
        limit=limit,
    )
    qc.set(cache_key, result, ttl=60.0)
    return result


@router.post(
    "/signals",
    response_model=AbsenceSignal,
    status_code=201,
    summary="Create absence signal",
)
def create_signal(
    req: AbsenceSignalCreateRequest,
    _user: UserClaims = Depends(require_operator),
) -> AbsenceSignal:
    return _svc().create_signal(req)


# ── Signal item endpoints ─────────────────────────────────────────────────────


@router.get(
    "/signals/{signal_id}",
    response_model=AbsenceSignal,
    summary="Get absence signal",
)
def get_signal(signal_id: str) -> AbsenceSignal:
    return _get_signal_or_404(signal_id)


@router.post(
    "/signals/{signal_id}/resolve",
    response_model=AbsenceSignal,
    summary="Resolve absence signal",
)
def resolve_signal(
    signal_id: str,
    gap_end: datetime = Body(
        ...,
        description="UTC-aware datetime when the absence resolved",
        embed=True,
    ),
    _user: UserClaims = Depends(require_operator),
) -> AbsenceSignal:
    _get_signal_or_404(signal_id)  # validate existence first
    updated = _svc().resolve_signal(signal_id, gap_end)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id!r} not found")
    return updated


@router.post(
    "/signals/{signal_id}/link-event",
    response_model=AbsenceSignal,
    summary="Link canonical event to absence signal",
)
def link_event(
    signal_id: str,
    event_id: str = Body(..., description="Canonical event ID to link", embed=True),
    _user: UserClaims = Depends(require_operator),
) -> AbsenceSignal:
    _get_signal_or_404(signal_id)  # validate existence first
    updated = _svc().link_event(signal_id, event_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id!r} not found")
    return updated


# ── Alerts ────────────────────────────────────────────────────────────────────


@router.get(
    "/alerts",
    response_model=List[AbsenceAlert],
    summary="List absence alerts",
)
def list_alerts(
    min_severity: AbsenceSeverity = Query(
        default=AbsenceSeverity.MEDIUM,
        description="Minimum severity to include in alerts",
    ),
) -> List[AbsenceAlert]:
    return _svc().generate_alerts(min_severity=min_severity)


# ── Analytics summary ─────────────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=AbsenceAnalyticsSummary,
    summary="Absence analytics summary",
)
def get_summary(
    start: datetime = Query(
        default=None,
        description="Window start (UTC-aware ISO 8601); defaults to 30 days ago",
    ),
    end: datetime = Query(
        default=None,
        description="Window end (UTC-aware ISO 8601); defaults to now",
    ),
) -> AbsenceAnalyticsSummary:
    now = datetime.now(timezone.utc)
    window_start = start if start is not None else now.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - __import__("datetime").timedelta(days=30)
    window_end = end if end is not None else now
    return _svc().get_summary(window_start=window_start, window_end=window_end)


# ── Scan ──────────────────────────────────────────────────────────────────────


@router.post(
    "/scan/ais-gaps",
    response_model=List[AbsenceSignal],
    summary="Trigger AIS gap detection scan",
)
def scan_ais_gaps(
    min_gap_seconds: float = Query(
        default=1800.0,
        ge=60.0,
        description="Minimum gap duration in seconds to flag as an absence signal",
    ),
    confidence_threshold: float = Query(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score to emit a signal",
    ),
    _user: UserClaims = Depends(require_operator),
    _rl: None = Depends(heavy_endpoint_rate_limit),
) -> List[AbsenceSignal]:
    """Scan telemetry store for vessels whose AIS stream has gone silent.

    Returns newly created absence signals.  If no telemetry data is loaded,
    the result is an empty list.
    """
    from src.api.events import _store as _telemetry_event_store  # noqa: PLC0415
    # We need the TelemetryStore.  It is the module-level singleton in the
    # telemetry store module.
    try:
        from src.services.telemetry_store import TelemetryStore as _TS  # noqa: PLC0415
        # Walk the event store's shared telemetry store if it was bound at startup
        from src.api import imagery as _imagery_mod  # noqa: PLC0415
        ts = getattr(_imagery_mod, "_telemetry_store", None)
        if ts is None:
            # Fall back to a fresh empty store (no data yet)
            ts = _TS()
    except Exception:  # noqa: BLE001
        from src.services.telemetry_store import TelemetryStore as _TS  # noqa: PLC0415
        ts = _TS()

    return _svc().detect_ais_gaps(
        telemetry_store=ts,
        min_gap_seconds=min_gap_seconds,
        confidence_threshold=confidence_threshold,
    )
