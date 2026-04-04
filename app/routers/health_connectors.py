"""Connector health and in-process metrics endpoints — Phase 6 Track C.

Routes
------
  GET /api/v1/health/connectors  — per-connector health summary (name, last
                                    fetch time, error count, health status)
  GET /api/v1/health/metrics     — current in-process metrics snapshot as JSON
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

from app import metrics as _metrics
from src.services.source_health import get_health_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["connector-health"])


def _derive_status(record: Any) -> str:
    """Map a SourceHealthRecord to one of: healthy | degraded | unknown."""
    if record.freshness_status == "fresh":
        return "healthy"
    if record.freshness_status in ("stale", "critical"):
        return "degraded"
    # Fall back to the is_healthy flag when freshness is unknown
    if record.total_requests == 0:
        return "unknown"
    return "healthy" if record.is_healthy else "degraded"


@router.get(
    "/connectors",
    summary="Per-connector health summary",
    response_model=None,
)
def get_connector_health() -> Dict[str, Any]:
    """Return name, last fetch time, error count, and health status for every
    registered connector.  Healthy means the connector is reachable and
    has delivered data within its SLA window.
    """
    svc = get_health_service()
    dashboard = svc.get_dashboard()

    connectors = []
    for r in dashboard.connectors:
        last_fetch: str | None = None
        if r.last_successful_poll:
            last_fetch = r.last_successful_poll.isoformat()
            # Mirror into metrics so the /metrics endpoint stays current
            _metrics.set_connector_last_fetch(
                r.connector_id, r.last_successful_poll.timestamp()
            )

        connectors.append(
            {
                "connector_id": r.connector_id,
                "display_name": r.display_name,
                "source_type": r.source_type,
                "status": _derive_status(r),
                "last_successful_fetch": last_fetch,
                "error_count": r.total_errors,
                "consecutive_errors": r.consecutive_errors,
                "freshness_status": r.freshness_status,
                "freshness_age_minutes": r.freshness_age_minutes,
            }
        )

    healthy = sum(1 for c in connectors if c["status"] == "healthy")
    degraded = sum(1 for c in connectors if c["status"] == "degraded")
    unknown = sum(1 for c in connectors if c["status"] == "unknown")

    return {
        "connectors": connectors,
        "overall_healthy": dashboard.overall_healthy,
        "total_connectors": len(connectors),
        "healthy_count": healthy,
        "degraded_count": degraded,
        "unknown_count": unknown,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/metrics",
    summary="In-process metrics snapshot",
    response_model=None,
)
def get_metrics_snapshot() -> Dict[str, Any]:
    """Return the current in-process metrics registry snapshot.

    The payload contains three top-level sections:
    - ``counters``   — cumulative counts (connector_error_count, evidence_pack_exports_total, …)
    - ``gauges``     — point-in-time values (connector_last_fetch_timestamp, active_investigations_total)
    - ``histograms`` — distribution summaries with count, sum, p50, p95, p99
    """
    return _metrics.snapshot()
