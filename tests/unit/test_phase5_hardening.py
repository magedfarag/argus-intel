"""Tests for Phase 5 production hardening.

Covers:
  P5-1.5: Server-side density reduction in event search
  P5-3.1: Health dashboard API endpoints
  P5-2.1/2.2: Celery beat tasks and queue configuration
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.events import (
    _apply_density_reduction,
    _DENSITY_THRESHOLD,
    _DENSITY_MAX_RESULTS,
)
from src.models.event_search import EventSearchResponse
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.services.source_health import FreshnessSLA, SourceHealthService
from src.api.source_health import set_api_health_service


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_event(idx: int) -> CanonicalEvent:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=idx)
    return CanonicalEvent(
        event_id=make_event_id("test", f"entity_{idx}", ts.isoformat()),
        event_time=ts,
        ingested_at=ts,
        source="test",
        source_type=SourceType.CONTEXT_FEED,
        entity_type=EntityType.NEWS_ARTICLE,
        event_type=EventType.CONTEXTUAL_EVENT,
        geometry={"type": "Point", "coordinates": [55.0, 25.0]},
        centroid={"type": "Point", "coordinates": [55.0, 25.0]},
        normalization=NormalizationRecord(normalized_by="test"),
        provenance=ProvenanceRecord(raw_source_ref="test://source"),
        license=LicenseRecord(),
        correlation_keys=CorrelationKeys(),
    )


def _make_response(n: int) -> EventSearchResponse:
    return EventSearchResponse(
        events=[_make_event(i) for i in range(n)],
        total=n,
        page=1,
        page_size=n,
        has_next=False,
    )


# ── P5-1.5: Density reduction ──────────────────────────────────────────────────


class TestDensityReduction:

    def test_no_reduction_below_threshold(self):
        resp = _make_response(100)
        result = _apply_density_reduction(resp)
        assert result.was_reduced is False
        assert len(result.events) == 100

    def test_no_reduction_at_threshold(self):
        resp = _make_response(_DENSITY_THRESHOLD)
        result = _apply_density_reduction(resp)
        assert result.was_reduced is False
        assert len(result.events) == _DENSITY_THRESHOLD

    def test_reduction_above_threshold(self):
        resp = _make_response(_DENSITY_THRESHOLD + 1)
        result = _apply_density_reduction(resp)
        assert result.was_reduced is True
        assert len(result.events) == _DENSITY_MAX_RESULTS

    def test_reduced_total_preserves_original_count(self):
        n = _DENSITY_THRESHOLD + 100
        resp = _make_response(n)
        result = _apply_density_reduction(resp)
        assert result.total == n

    def test_reduced_events_are_time_sorted(self):
        resp = _make_response(_DENSITY_THRESHOLD + 50)
        result = _apply_density_reduction(resp)
        times = [e.event_time for e in result.events]
        assert times == sorted(times)

    def test_reduction_is_deterministic(self):
        """Same input always produces the same sample."""
        resp1 = _make_response(_DENSITY_THRESHOLD + 200)
        resp2 = _make_response(_DENSITY_THRESHOLD + 200)
        r1 = _apply_density_reduction(resp1)
        r2 = _apply_density_reduction(resp2)
        assert [e.event_id for e in r1.events] == [e.event_id for e in r2.events]


# ── P5-3.1: Health dashboard API ───────────────────────────────────────────────


class TestHealthDashboardAPI:

    @pytest.fixture(autouse=True)
    def setup_client(self, app_client: TestClient) -> None:
        self.svc = SourceHealthService(sla_config=[
            FreshnessSLA(
                connector_id="gdelt",
                display_name="GDELT",
                max_age_minutes=30,
                critical_age_minutes=120,
            )
        ])
        set_api_health_service(self.svc)
        self.client = app_client

    def test_get_health_dashboard_empty(self):
        resp = self.client.get("/api/v1/health/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "connectors" in data
        assert "alerts" in data
        assert data["overall_healthy"] is True

    def test_get_health_dashboard_with_connector(self):
        self.svc.record_success("gdelt", "GDELT", "context")
        resp = self.client.get("/api/v1/health/sources")
        assert resp.status_code == 200
        connectors = resp.json()["connectors"]
        assert any(c["connector_id"] == "gdelt" for c in connectors)
        gdelt = next(c for c in connectors if c["connector_id"] == "gdelt")
        assert gdelt["is_healthy"] is True
        assert gdelt["freshness_status"] == "fresh"

    def test_get_connector_detail_found(self):
        self.svc.record_success("gdelt", "GDELT", "context")
        resp = self.client.get("/api/v1/health/sources/gdelt")
        assert resp.status_code == 200
        assert resp.json()["connector_id"] == "gdelt"

    def test_get_connector_detail_not_found(self):
        resp = self.client.get("/api/v1/health/sources/nonexistent-connector")
        assert resp.status_code == 404

    def test_get_alerts_empty(self):
        resp = self.client.get("/api/v1/health/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_usage_endpoint(self):
        self.svc.record_success("gdelt")
        resp = self.client.get("/api/v1/health/usage")
        assert resp.status_code == 200
        usage = resp.json()
        assert isinstance(usage, list)
        assert any(u["connector_id"] == "gdelt" for u in usage)

    def test_overall_healthy_false_when_unhealthy(self):
        self.svc.record_error("gdelt", "fail")
        resp = self.client.get("/api/v1/health/sources")
        assert resp.status_code == 200
        assert resp.json()["overall_healthy"] is False


# ── P5-2.1/2.2: Celery queue configuration ─────────────────────────────────────


class TestCeleryQueueConfig:

    def test_celery_beat_has_aisstream_task(self):
        """P5-2.1: AIS polling task is registered in the Celery beat schedule."""
        try:
            from app.workers.celery_app import celery_app
        except ImportError:
            pytest.skip("Celery not installed")
        if celery_app is None:
            pytest.skip("Celery not configured")
        schedule = celery_app.conf.beat_schedule
        assert "poll-aisstream-every-30s" in schedule
        assert schedule["poll-aisstream-every-30s"]["task"] == "poll_aisstream_positions"

    def test_celery_beat_has_retention_task(self):
        """P5-4.4: Retention enforcement task is registered in the Celery beat schedule."""
        try:
            from app.workers.celery_app import celery_app
        except ImportError:
            pytest.skip("Celery not installed")
        if celery_app is None:
            pytest.skip("Celery not configured")
        assert "enforce-telemetry-retention-every-hour" in celery_app.conf.beat_schedule

    def test_celery_queue_priorities_configured(self):
        """P5-2.2: Three priority queues are configured (high, default, low)."""
        try:
            from app.workers.celery_app import celery_app
        except ImportError:
            pytest.skip("Celery not installed")
        if celery_app is None:
            pytest.skip("Celery not configured")
        routes = celery_app.conf.task_routes
        assert routes.get("run_analysis_task", {}).get("queue") == "high"
        assert routes.get("run_export_task", {}).get("queue") == "low"
        assert routes.get("poll_gdelt_context", {}).get("queue") == "default"
