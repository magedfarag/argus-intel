"""Unit tests for GET /api/v1/health/connectors and GET /api/v1/health/metrics
— Phase 6 Track C.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_record(
    connector_id: str,
    is_healthy: bool = True,
    freshness_status: str = "unknown",
    total_errors: int = 0,
    consecutive_errors: int = 0,
    last_successful_poll: datetime | None = None,
    display_name: str = "",
    source_type: str = "test",
    total_requests: int = 0,
    freshness_age_minutes: float | None = None,
) -> Any:
    """Return a mock SourceHealthRecord-like object."""
    from types import SimpleNamespace

    return SimpleNamespace(
        connector_id=connector_id,
        display_name=display_name or connector_id,
        source_type=source_type,
        is_healthy=is_healthy,
        freshness_status=freshness_status,
        total_errors=total_errors,
        consecutive_errors=consecutive_errors,
        last_successful_poll=last_successful_poll,
        total_requests=total_requests,
        freshness_age_minutes=freshness_age_minutes,
    )


def _make_dashboard(connectors: list, overall_healthy: bool = True) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        connectors=connectors,
        overall_healthy=overall_healthy,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app, raise_server_exceptions=True)


# ── GET /api/v1/health/connectors ─────────────────────────────────────────────


def test_connectors_endpoint_returns_200(client: TestClient):
    resp = client.get("/api/v1/health/connectors")
    assert resp.status_code == 200


def test_connectors_response_has_required_keys(client: TestClient):
    resp = client.get("/api/v1/health/connectors")
    body = resp.json()
    for key in ("connectors", "overall_healthy", "total_connectors", "generated_at"):
        assert key in body, f"Missing key: {key}"


def test_connectors_list_is_a_list(client: TestClient):
    resp = client.get("/api/v1/health/connectors")
    body = resp.json()
    assert isinstance(body["connectors"], list)


def test_connector_entries_have_expected_fields(client: TestClient):
    resp = client.get("/api/v1/health/connectors")
    body = resp.json()
    required_fields = {
        "connector_id",
        "display_name",
        "source_type",
        "status",
        "error_count",
        "consecutive_errors",
        "freshness_status",
    }
    for entry in body["connectors"]:
        for field in required_fields:
            assert field in entry, f"Missing field '{field}' in connector entry"


def test_connector_status_is_valid_value(client: TestClient):
    resp = client.get("/api/v1/health/connectors")
    body = resp.json()
    valid_statuses = {"healthy", "degraded", "unknown"}
    for entry in body["connectors"]:
        assert entry["status"] in valid_statuses, (
            f"Unexpected status '{entry['status']}' for {entry['connector_id']}"
        )


def test_connector_status_healthy_for_fresh_record():
    """_derive_status returns 'healthy' when freshness_status == 'fresh'."""
    from app.routers.health_connectors import _derive_status

    rec = _make_record("test", is_healthy=True, freshness_status="fresh", total_requests=1)
    assert _derive_status(rec) == "healthy"


def test_connector_status_degraded_for_stale_record():
    from app.routers.health_connectors import _derive_status

    rec = _make_record("test", is_healthy=False, freshness_status="stale", total_requests=3)
    assert _derive_status(rec) == "degraded"


def test_connector_status_unknown_for_zero_requests():
    from app.routers.health_connectors import _derive_status

    rec = _make_record("test", is_healthy=False, freshness_status="unknown", total_requests=0)
    assert _derive_status(rec) == "unknown"


def test_connector_status_healthy_fallback_when_is_healthy_true():
    from app.routers.health_connectors import _derive_status

    rec = _make_record("test", is_healthy=True, freshness_status="unknown", total_requests=5)
    assert _derive_status(rec) == "healthy"


def test_endpoint_counts_healthy_degraded_unknown(client: TestClient):
    """healthy_count + degraded_count + unknown_count should equal total_connectors."""
    resp = client.get("/api/v1/health/connectors")
    body = resp.json()
    total = body["total_connectors"]
    derived = body["healthy_count"] + body["degraded_count"] + body["unknown_count"]
    assert derived == total


def test_dashboard_last_fetch_is_iso_string_or_null(client: TestClient):
    resp = client.get("/api/v1/health/connectors")
    body = resp.json()
    for c in body["connectors"]:
        val = c.get("last_successful_fetch")
        if val is not None:
            # Should be parseable as ISO 8601
            datetime.fromisoformat(val.replace("Z", "+00:00"))


def test_connectors_endpoint_does_not_raise_on_empty_health_service():
    """Endpoint should return 200 even when no connectors are registered."""
    from unittest.mock import MagicMock

    from app.routers.health_connectors import get_connector_health

    mock_svc = MagicMock()
    mock_svc.get_dashboard.return_value = _make_dashboard(connectors=[], overall_healthy=True)

    with patch("app.routers.health_connectors.get_health_service", return_value=mock_svc):
        result = get_connector_health()

    assert result["total_connectors"] == 0
    assert result["overall_healthy"] is True


# ── GET /api/v1/health/metrics ────────────────────────────────────────────────


def test_metrics_endpoint_returns_200(client: TestClient):
    resp = client.get("/api/v1/health/metrics")
    assert resp.status_code == 200


def test_metrics_response_has_at_least_3_top_level_keys(client: TestClient):
    resp = client.get("/api/v1/health/metrics")
    body = resp.json()
    assert len(body) >= 3, f"Expected >= 3 keys, got: {list(body.keys())}"


def test_metrics_response_contains_counters_gauges_histograms(client: TestClient):
    resp = client.get("/api/v1/health/metrics")
    body = resp.json()
    for section in ("counters", "gauges", "histograms"):
        assert section in body, f"Missing section: {section}"


def test_metrics_snapshot_at_is_a_float(client: TestClient):
    resp = client.get("/api/v1/health/metrics")
    body = resp.json()
    assert isinstance(body.get("snapshot_at"), float)
