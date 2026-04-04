"""Source health dashboard API — P5-3.1.

GET /api/v1/health/sources        — list all connector health records
GET /api/v1/health/sources/{id}   — single connector health detail
GET /api/v1/health/alerts         — active SLA breach alerts
GET /api/v1/health/usage          — hourly API usage per connector
POST /api/v1/health/sources/{id}/enable  — re-enable a disabled connector (P5-3.5)
POST /api/v1/health/sources/{id}/disable — disable a connector (P5-3.5)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.services.source_health import (
    HealthDashboardResponse,
    HealthAlert,
    SourceHealthRecord,
    SourceHealthService,
    UsagePeriod,
    get_health_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["health-dashboard"])

# ── Module-level service (replaced in tests via set_api_health_service) ────────
_svc: Optional[SourceHealthService] = None


def get_api_health_service() -> SourceHealthService:
    return _svc if _svc is not None else get_health_service()


def set_api_health_service(svc: SourceHealthService) -> None:
    global _svc
    _svc = svc


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/sources",
    response_model=HealthDashboardResponse,
    summary="Full source health dashboard — connector statuses + alerts",
)
def get_health_dashboard() -> HealthDashboardResponse:
    """Return the full health dashboard: connector statuses, freshness, and open alerts."""
    return get_api_health_service().get_dashboard()


@router.get(
    "/sources/{connector_id}",
    response_model=SourceHealthRecord,
    summary="Single connector health record",
)
def get_connector_health(connector_id: str) -> SourceHealthRecord:
    """Return freshness and error statistics for a single connector."""
    svc = get_api_health_service()
    dashboard = svc.get_dashboard()
    match = next((r for r in dashboard.connectors if r.connector_id == connector_id), None)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found",
        )
    return match


@router.get(
    "/alerts",
    response_model=List[HealthAlert],
    summary="Active SLA breach alerts",
)
def get_alerts(
    include_resolved: bool = Query(default=False, description="Include resolved alerts"),
) -> List[HealthAlert]:
    """Return the list of SLA breach alerts.  By default only open (unresolved) alerts."""
    svc = get_api_health_service()
    dashboard = svc.get_dashboard()
    if include_resolved:
        # Dashboard only carries open alerts; re-query internal state
        with svc._lock:
            return list(svc._alerts.values())
    return dashboard.alerts


@router.get(
    "/usage",
    response_model=List[UsagePeriod],
    summary="Hourly API usage per connector (P5-3.4 cost tracking)",
)
def get_usage() -> List[UsagePeriod]:
    """Return per-connector API call counts for the last 60 minutes."""
    return get_api_health_service().get_usage()
