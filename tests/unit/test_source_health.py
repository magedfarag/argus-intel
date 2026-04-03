"""Unit tests for SourceHealthService — P5-3.1, P5-3.2, P5-3.4."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.services.source_health import (
    FreshnessSLA,
    HealthAlert,
    SourceHealthService,
    get_health_service,
    set_health_service,
)


@pytest.fixture
def svc() -> SourceHealthService:
    sla = [
        FreshnessSLA(
            connector_id="gdelt",
            display_name="GDELT",
            max_age_minutes=30,
            critical_age_minutes=120,
            is_paid=False,
        ),
        FreshnessSLA(
            connector_id="planet",
            display_name="Planet",
            max_age_minutes=15,
            critical_age_minutes=60,
            is_paid=True,
            max_requests_per_hour=100,
        ),
    ]
    return SourceHealthService(sla_config=sla)


# ── record_success / record_error ─────────────────────────────────────────────

def test_record_success_marks_healthy(svc: SourceHealthService):
    svc.record_success("gdelt", "GDELT", "context")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.is_healthy is True
    assert rec.total_requests == 1
    assert rec.consecutive_errors == 0


def test_record_error_marks_unhealthy(svc: SourceHealthService):
    svc.record_error("gdelt", "Connection refused", "GDELT", "context")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.is_healthy is False
    assert rec.total_errors == 1
    assert rec.consecutive_errors == 1
    assert "Connection refused" in rec.last_error_message


def test_multiple_errors_accumulate(svc: SourceHealthService):
    svc.record_error("gdelt", "err1")
    svc.record_error("gdelt", "err2")
    svc.record_error("gdelt", "err3")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.consecutive_errors == 3
    assert rec.total_errors == 3


def test_success_resets_consecutive_errors(svc: SourceHealthService):
    svc.record_error("gdelt", "err1")
    svc.record_error("gdelt", "err2")
    svc.record_success("gdelt")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.consecutive_errors == 0
    assert rec.is_healthy is True


# ── Freshness evaluation ───────────────────────────────────────────────────────

def test_freshness_status_fresh_for_recent_poll(svc: SourceHealthService):
    svc.record_success("gdelt")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.freshness_status == "fresh"
    assert rec.freshness_age_minutes is not None
    assert rec.freshness_age_minutes < 1.0


def test_freshness_unknown_when_never_polled(svc: SourceHealthService):
    svc.record_error("gdelt", "err")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.freshness_status == "unknown"


# ── SLA alert generation ───────────────────────────────────────────────────────

def test_no_alert_for_fresh_connector(svc: SourceHealthService):
    svc.record_success("gdelt")
    d = svc.get_dashboard()
    assert len(d.alerts) == 0


def test_alert_resolved_on_recovery(svc: SourceHealthService):
    svc.record_success("gdelt")
    # Manually patch last_successful_poll to 2 hours ago to force critical
    old_time = datetime.now(timezone.utc) - timedelta(hours=3)
    with svc._lock:
        svc._records["gdelt"]["last_successful_poll"] = old_time
    d = svc.get_dashboard()
    alert_ids_before = {a.alert_id for a in d.alerts}
    assert len(alert_ids_before) > 0, "Expected at least one alert"
    # Recovery
    svc.record_success("gdelt")
    d2 = svc.get_dashboard()
    assert all(a.resolved for a in d2.alerts if a.alert_id in alert_ids_before)


# ── Usage tracking (P5-3.4) ───────────────────────────────────────────────────

def test_requests_last_hour_tracked(svc: SourceHealthService):
    for _ in range(5):
        svc.record_success("gdelt")
    d = svc.get_dashboard()
    rec = next(r for r in d.connectors if r.connector_id == "gdelt")
    assert rec.requests_last_hour == 5


def test_usage_endpoint_returns_period(svc: SourceHealthService):
    svc.record_success("planet", "Planet", "imagery")
    svc.record_success("planet", "Planet", "imagery")
    usage = svc.get_usage()
    planet_usage = next((u for u in usage if u.connector_id == "planet"), None)
    assert planet_usage is not None
    assert planet_usage.request_count == 2
    assert planet_usage.is_paid is True


# ── P5-2.4: Quota enforcement ─────────────────────────────────────────────────

def test_is_over_quota_false_when_under_limit(svc: SourceHealthService):
    for _ in range(50):
        svc.record_success("planet")
    assert svc.is_over_quota("planet") is False


def test_is_over_quota_true_when_at_limit(svc: SourceHealthService):
    for _ in range(100):
        svc.record_success("planet")
    assert svc.is_over_quota("planet") is True


def test_is_over_quota_false_for_unknown_connector(svc: SourceHealthService):
    assert svc.is_over_quota("unknown-connector") is False


# ── Overall health ────────────────────────────────────────────────────────────

def test_overall_healthy_true_when_all_healthy(svc: SourceHealthService):
    svc.record_success("gdelt")
    svc.record_success("planet")
    d = svc.get_dashboard()
    assert d.overall_healthy is True


def test_overall_healthy_false_when_any_unhealthy(svc: SourceHealthService):
    svc.record_success("gdelt")
    svc.record_error("planet", "fail")
    d = svc.get_dashboard()
    assert d.overall_healthy is False


def test_empty_dashboard_healthy(svc: SourceHealthService):
    d = svc.get_dashboard()
    assert d.overall_healthy is True


# ── Singleton helpers ─────────────────────────────────────────────────────────

def test_set_and_get_health_service():
    new_svc = SourceHealthService()
    set_health_service(new_svc)
    assert get_health_service() is new_svc
    # Restore
    set_health_service(None)  # type: ignore[arg-type]
