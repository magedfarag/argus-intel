"""Source health tracking, freshness SLAs, and usage monitoring.

P5-3.1: Per-connector freshness tracking and health dashboard data.
P5-3.2: Freshness SLA enforcement with staged alert thresholds.
P5-3.4: Cost/usage tracking for paid providers (API call count, period windows).
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ── SLA and policy models ──────────────────────────────────────────────────────

class FreshnessSLA(BaseModel):
    """Per-connector freshness SLA definition."""

    connector_id: str
    display_name: str = ""
    max_age_minutes: int = Field(
        default=30, ge=1,
        description="Warn if no successful poll within this window.",
    )
    critical_age_minutes: int = Field(
        default=120, ge=1,
        description="Critical alert if no successful poll within this window.",
    )
    is_paid: bool = Field(
        default=False, description="Whether the connector incurs API cost.",
    )
    max_requests_per_hour: Optional[int] = Field(
        default=None, description="Hard cap for paid connectors (P5-2.4).",
    )


# ── Response models ────────────────────────────────────────────────────────────

class SourceHealthRecord(BaseModel):
    """Per-connector health state for the dashboard."""

    connector_id: str
    display_name: str
    source_type: str
    is_healthy: bool
    last_successful_poll: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    consecutive_errors: int = 0
    total_requests: int = 0
    total_errors: int = 0
    freshness_status: str = "unknown"  # fresh | stale | critical | unknown
    freshness_age_minutes: Optional[float] = None
    requests_last_hour: int = 0


class HealthAlert(BaseModel):
    """Alert produced when a source SLA is breached."""

    alert_id: str
    connector_id: str
    severity: str  # warning | critical
    message: str
    triggered_at: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class UsagePeriod(BaseModel):
    """Cost/usage window for a single connector (P5-3.4)."""

    connector_id: str
    period_start: datetime
    period_end: datetime
    request_count: int = 0
    error_count: int = 0
    is_paid: bool = False


class HealthDashboardResponse(BaseModel):
    """Full health dashboard payload."""

    connectors: List[SourceHealthRecord]
    alerts: List[HealthAlert]
    overall_healthy: bool
    generated_at: datetime
    total_requests_last_hour: int = 0
    total_errors_last_hour: int = 0


# ── Service ────────────────────────────────────────────────────────────────────

class SourceHealthService:
    """Thread-safe, in-memory source health tracker.

    Tracks per-connector health state, freshness SLA compliance, and
    hourly API usage counters.  The interface is designed for a PostGIS
    persistence swap-in (P0-4 path): callers only interact via this service,
    never directly with the internal dicts.
    """

    # Rolling window for per-hour rate tracking
    _HOUR = timedelta(hours=1)

    def __init__(self, sla_config: Optional[List[FreshnessSLA]] = None) -> None:
        self._lock = threading.Lock()
        # connector_id -> mutable dict of health fields
        self._records: Dict[str, Dict[str, Any]] = {}
        # connector_id -> list of request timestamps (within last hour)
        self._request_log: Dict[str, List[datetime]] = {}
        # alert_id -> HealthAlert
        self._alerts: Dict[str, HealthAlert] = {}
        # connector_id -> FreshnessSLA
        self._slas: Dict[str, FreshnessSLA] = {}

        for sla in (sla_config or []):
            self._slas[sla.connector_id] = sla

    # ── Public write API ───────────────────────────────────────────────────────

    def record_success(
        self,
        connector_id: str,
        display_name: str = "",
        source_type: str = "unknown",
    ) -> None:
        """Record a successful connector poll / fetch."""
        now = datetime.now(timezone.utc)
        with self._lock:
            rec = self._get_or_create(connector_id, display_name, source_type)
            rec["is_healthy"] = True
            rec["last_successful_poll"] = now
            rec["consecutive_errors"] = 0
            rec["total_requests"] = rec["total_requests"] + 1
            if display_name:
                rec["display_name"] = display_name
            if source_type and source_type != "unknown":
                rec["source_type"] = source_type
            self._log_request(connector_id, now)
            self._resolve_stale_alert(connector_id, now)

    def record_error(
        self,
        connector_id: str,
        error_msg: str,
        display_name: str = "",
        source_type: str = "unknown",
    ) -> None:
        """Record a connector failure."""
        now = datetime.now(timezone.utc)
        with self._lock:
            rec = self._get_or_create(connector_id, display_name, source_type)
            rec["is_healthy"] = False
            rec["last_error_at"] = now
            rec["last_error_message"] = error_msg[:500]
            rec["consecutive_errors"] = rec["consecutive_errors"] + 1
            rec["total_requests"] = rec["total_requests"] + 1
            rec["total_errors"] = rec["total_errors"] + 1
            if display_name:
                rec["display_name"] = display_name
            if source_type and source_type != "unknown":
                rec["source_type"] = source_type
            self._log_request(connector_id, now)

    # ── Public read API ────────────────────────────────────────────────────────

    def get_dashboard(self) -> HealthDashboardResponse:
        """Return full dashboard snapshot with freshness + SLA evaluation."""
        now = datetime.now(timezone.utc)
        with self._lock:
            records = [self._build_health_record(cid, rec, now) for cid, rec in self._records.items()]
            active_alerts = [a for a in self._alerts.values() if not a.resolved]
            self._evaluate_sla_alerts(now)
            # Re-read after SLA pass
            active_alerts = [a for a in self._alerts.values() if not a.resolved]

        total_req = sum(r.requests_last_hour for r in records)
        total_err = sum(
            len([ts for ts in self._request_log.get(r.connector_id, []) if ts >= now - self._HOUR])
            for r in records
        )
        return HealthDashboardResponse(
            connectors=records,
            alerts=active_alerts,
            overall_healthy=all(r.is_healthy for r in records) if records else True,
            generated_at=now,
            total_requests_last_hour=total_req,
            total_errors_last_hour=sum(r.total_errors for r in records),
        )

    def get_usage(self) -> List[UsagePeriod]:
        """Return per-connector usage for the last hour."""
        now = datetime.now(timezone.utc)
        cutoff = now - self._HOUR
        result: List[UsagePeriod] = []
        with self._lock:
            for cid, timestamps in self._request_log.items():
                recent = [ts for ts in timestamps if ts >= cutoff]
                sla = self._slas.get(cid)
                result.append(UsagePeriod(
                    connector_id=cid,
                    period_start=cutoff,
                    period_end=now,
                    request_count=len(recent),
                    is_paid=sla.is_paid if sla else False,
                ))
        return result

    def is_over_quota(self, connector_id: str) -> bool:
        """Return True if connector has exceeded its hourly request cap (P5-2.4)."""
        sla = self._slas.get(connector_id)
        if not sla or not sla.max_requests_per_hour:
            return False
        now = datetime.now(timezone.utc)
        cutoff = now - self._HOUR
        with self._lock:
            recent = [ts for ts in self._request_log.get(connector_id, []) if ts >= cutoff]
        return len(recent) >= sla.max_requests_per_hour

    def register_sla(self, sla: FreshnessSLA) -> None:
        """Register or update an SLA definition."""
        with self._lock:
            self._slas[sla.connector_id] = sla

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _get_or_create(
        self, connector_id: str, display_name: str, source_type: str
    ) -> Dict[str, Any]:
        if connector_id not in self._records:
            self._records[connector_id] = {
                "connector_id": connector_id,
                "display_name": display_name or connector_id,
                "source_type": source_type,
                "is_healthy": True,
                "last_successful_poll": None,
                "last_error_at": None,
                "last_error_message": None,
                "consecutive_errors": 0,
                "total_requests": 0,
                "total_errors": 0,
            }
        return self._records[connector_id]

    def _log_request(self, connector_id: str, ts: datetime) -> None:
        """Append timestamp; prune entries older than 1 hour."""
        lst = self._request_log.setdefault(connector_id, [])
        lst.append(ts)
        cutoff = ts - self._HOUR
        self._request_log[connector_id] = [t for t in lst if t >= cutoff]

    def _build_health_record(
        self, connector_id: str, rec: Dict[str, Any], now: datetime
    ) -> SourceHealthRecord:
        sla = self._slas.get(connector_id)
        freshness_status = "unknown"
        freshness_age_min: Optional[float] = None

        last_poll = rec.get("last_successful_poll")
        if last_poll:
            age_min = (now - last_poll).total_seconds() / 60.0
            freshness_age_min = round(age_min, 1)
            if sla:
                if age_min >= sla.critical_age_minutes:
                    freshness_status = "critical"
                elif age_min >= sla.max_age_minutes:
                    freshness_status = "stale"
                else:
                    freshness_status = "fresh"
            else:
                freshness_status = "fresh" if age_min < 30 else "stale"

        cutoff = now - self._HOUR
        recent = [t for t in self._request_log.get(connector_id, []) if t >= cutoff]

        return SourceHealthRecord(
            connector_id=connector_id,
            display_name=rec.get("display_name", connector_id),
            source_type=rec.get("source_type", "unknown"),
            is_healthy=rec.get("is_healthy", False),
            last_successful_poll=rec.get("last_successful_poll"),
            last_error_at=rec.get("last_error_at"),
            last_error_message=rec.get("last_error_message"),
            consecutive_errors=rec.get("consecutive_errors", 0),
            total_requests=rec.get("total_requests", 0),
            total_errors=rec.get("total_errors", 0),
            freshness_status=freshness_status,
            freshness_age_minutes=freshness_age_min,
            requests_last_hour=len(recent),
        )

    def _resolve_stale_alert(self, connector_id: str, now: datetime) -> None:
        """Mark any open stale/critical alert for this connector as resolved."""
        for alert in self._alerts.values():
            if alert.connector_id == connector_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = now

    def _evaluate_sla_alerts(self, now: datetime) -> None:
        """Raise new alerts for connectors failing their SLA."""
        for connector_id, sla in self._slas.items():
            rec = self._records.get(connector_id)
            if not rec:
                continue
            last_poll = rec.get("last_successful_poll")
            if not last_poll:
                continue
            age_min = (now - last_poll).total_seconds() / 60.0

            severity: Optional[str] = None
            if age_min >= sla.critical_age_minutes:
                severity = "critical"
            elif age_min >= sla.max_age_minutes:
                severity = "warning"

            if severity:
                # Only raise a new alert if no open one exists
                open_alert = next(
                    (a for a in self._alerts.values()
                     if a.connector_id == connector_id and not a.resolved),
                    None,
                )
                if not open_alert:
                    alert_id = str(uuid.uuid4())
                    self._alerts[alert_id] = HealthAlert(
                        alert_id=alert_id,
                        connector_id=connector_id,
                        severity=severity,
                        message=(
                            f"{sla.display_name or connector_id}: no successful poll "
                            f"for {age_min:.0f} min (SLA: {sla.max_age_minutes} min)"
                        ),
                        triggered_at=now,
                    )
                    log.warning(
                        "SLA breach [%s] connector=%s age=%.0f min",
                        severity, connector_id, age_min,
                    )


# ── Module-level singleton ─────────────────────────────────────────────────────

_health_service: Optional[SourceHealthService] = None


def get_health_service() -> SourceHealthService:
    """Return the module-level singleton (lazily initialised)."""
    global _health_service
    if _health_service is None:
        _health_service = SourceHealthService()
    return _health_service


def set_health_service(svc: SourceHealthService) -> None:
    """Replace the singleton (used in tests)."""
    global _health_service
    _health_service = svc
