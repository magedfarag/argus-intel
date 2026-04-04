"""Integration tests for the Absence-As-Signal API — Phase 5 Track D.

Uses FastAPI TestClient via the shared app_client fixture from conftest.py.
Each test clears the absence service store before running to avoid
cross-test pollution.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from src.services.absence_analytics import get_default_absence_service


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

BASE = "/api/v1/absence"
_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_store():
    """Wipe the absence service store before every test."""
    get_default_absence_service().clear()
    yield
    get_default_absence_service().clear()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _create_signal(client: TestClient, **overrides) -> dict:
    payload = {
        "signal_type": "ais_gap",
        "entity_id": "MMSI-999000001",
        "entity_type": "vessel",
        "gap_start": (_NOW - timedelta(hours=3)).isoformat(),
        "severity": "high",
        "confidence": 0.8,
        "detection_method": "gap_detection",
        "provenance": {"source": "test"},
    }
    payload.update(overrides)
    r = client.post(f"{BASE}/signals", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ──────────────────────────────────────────────────────────────────────────────
# 1. POST /signals — create signal
# ──────────────────────────────────────────────────────────────────────────────


def test_create_signal_returns_201(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/signals",
        json={
            "signal_type": "ais_gap",
            "entity_id": "MMSI-100",
            "entity_type": "vessel",
            "gap_start": (_NOW - timedelta(hours=2)).isoformat(),
            "severity": "high",
            "confidence": 0.85,
            "detection_method": "gap_detection",
            "provenance": {"source": "aisstream"},
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["signal_id"]
    assert data["signal_type"] == "ais_gap"
    assert data["entity_id"] == "MMSI-100"
    assert data["severity"] == "high"


def test_create_signal_with_all_fields(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/signals",
        json={
            "signal_type": "camera_silence",
            "entity_id": "CAM-GATE-01",
            "entity_type": "camera",
            "gap_start": (_NOW - timedelta(hours=1)).isoformat(),
            "gap_end": _NOW.isoformat(),
            "expected_interval_seconds": 30.0,
            "severity": "medium",
            "confidence": 0.75,
            "detection_method": "feed_monitor",
            "provenance": {"source": "camera-feed"},
            "notes": "Scheduled maintenance window",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["signal_type"] == "camera_silence"
    assert data["notes"] == "Scheduled maintenance window"
    assert data["gap_end"] is not None


def test_create_assigns_unique_signal_ids(app_client: TestClient):
    a = _create_signal(app_client, entity_id="MMSI-A")
    b = _create_signal(app_client, entity_id="MMSI-B")
    assert a["signal_id"] != b["signal_id"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. GET /signals — list signals
# ──────────────────────────────────────────────────────────────────────────────


def test_list_signals_returns_list(app_client: TestClient):
    _create_signal(app_client)
    r = app_client.get(f"{BASE}/signals")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_list_signals_empty_after_clear(app_client: TestClient):
    r = app_client.get(f"{BASE}/signals")
    assert r.status_code == 200
    assert r.json() == []


def test_list_signals_signal_type_filter(app_client: TestClient):
    _create_signal(app_client, signal_type="ais_gap", entity_id="MMSI-AIS")
    _create_signal(app_client, signal_type="camera_silence", entity_id="CAM-01")
    r = app_client.get(f"{BASE}/signals?signal_type=ais_gap")
    assert r.status_code == 200
    data = r.json()
    assert all(s["signal_type"] == "ais_gap" for s in data)


def test_list_signals_active_only_filter(app_client: TestClient):
    # Active (no gap_end)
    _create_signal(app_client, entity_id="MMSI-ACTIVE")
    # Resolved (gap_end set)
    _create_signal(
        app_client,
        entity_id="MMSI-RESOLVED",
        gap_end=_NOW.isoformat(),
    )
    r = app_client.get(f"{BASE}/signals?active_only=true")
    assert r.status_code == 200
    data = r.json()
    assert all(s["gap_end"] is None for s in data)
    assert any(s["entity_id"] == "MMSI-ACTIVE" for s in data)


def test_list_signals_min_confidence_filter(app_client: TestClient):
    _create_signal(app_client, entity_id="HIGH-CONF", confidence=0.9)
    _create_signal(app_client, entity_id="LOW-CONF", confidence=0.3)
    r = app_client.get(f"{BASE}/signals?min_confidence=0.7")
    assert r.status_code == 200
    data = r.json()
    assert all(s["confidence"] >= 0.7 for s in data)


# ──────────────────────────────────────────────────────────────────────────────
# 3. GET /signals/{signal_id} — get single signal
# ──────────────────────────────────────────────────────────────────────────────


def test_get_signal_returns_signal(app_client: TestClient):
    created = _create_signal(app_client)
    sid = created["signal_id"]
    r = app_client.get(f"{BASE}/signals/{sid}")
    assert r.status_code == 200
    assert r.json()["signal_id"] == sid


def test_get_signal_404_for_missing(app_client: TestClient):
    r = app_client.get(f"{BASE}/signals/nonexistent-id-xyz")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# 4. POST /signals/{signal_id}/resolve — resolve signal
# ──────────────────────────────────────────────────────────────────────────────


def test_resolve_signal_sets_gap_end(app_client: TestClient):
    created = _create_signal(app_client)
    sid = created["signal_id"]
    gap_end_iso = _NOW.isoformat()
    r = app_client.post(
        f"{BASE}/signals/{sid}/resolve",
        json={"gap_end": gap_end_iso},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["resolved"] is True
    assert data["gap_end"] is not None


def test_resolve_signal_404_for_missing(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/signals/no-such-id/resolve",
        json={"gap_end": _NOW.isoformat()},
    )
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 5. POST /signals/{signal_id}/link-event — link event
# ──────────────────────────────────────────────────────────────────────────────


def test_link_event_adds_event_id(app_client: TestClient):
    created = _create_signal(app_client)
    sid = created["signal_id"]
    r = app_client.post(
        f"{BASE}/signals/{sid}/link-event",
        json={"event_id": "evt-canonical-001"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "evt-canonical-001" in data["related_event_ids"]


def test_link_event_404_for_missing_signal(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/signals/no-such-id/link-event",
        json={"event_id": "evt-001"},
    )
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 6. GET /alerts — list alerts
# ──────────────────────────────────────────────────────────────────────────────


def test_get_alerts_returns_list(app_client: TestClient):
    # Create a HIGH severity active signal that should trigger an alert
    _create_signal(
        app_client,
        severity="high",
        entity_id="MMSI-ALERT-01",
        gap_start=datetime.now(timezone.utc).isoformat(),
    )
    r = app_client.get(f"{BASE}/alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_alerts_min_severity_filter(app_client: TestClient):
    r = app_client.get(f"{BASE}/alerts?min_severity=critical")
    assert r.status_code == 200
    data = r.json()
    # All returned alerts must be CRITICAL severity
    assert all(a["severity"] == "critical" for a in data)


# ──────────────────────────────────────────────────────────────────────────────
# 7. GET /summary — analytics summary
# ──────────────────────────────────────────────────────────────────────────────


def test_get_summary_returns_summary(app_client: TestClient):
    _create_signal(app_client)
    window_start = (_NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = (_NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = app_client.get(f"{BASE}/summary?start={window_start}&end={window_end}")
    assert r.status_code == 200
    data = r.json()
    assert "total_signals" in data
    assert "by_type" in data
    assert "by_severity" in data
    assert "active_signals" in data
    assert "resolved_signals" in data
    assert "high_confidence_count" in data


def test_get_summary_counts_match(app_client: TestClient):
    _create_signal(app_client, entity_id="MMSI-ACTIVE", gap_start=(_NOW - timedelta(hours=2)).isoformat())
    _create_signal(app_client, entity_id="MMSI-RESOLVED", gap_start=(_NOW - timedelta(hours=2)).isoformat(), gap_end=_NOW.isoformat())
    window_start = (_NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = (_NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = app_client.get(f"{BASE}/summary?start={window_start}&end={window_end}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_signals"] == 2
    assert data["active_signals"] == 1
    assert data["resolved_signals"] == 1


def test_get_summary_no_params_uses_defaults(app_client: TestClient):
    r = app_client.get(f"{BASE}/summary")
    assert r.status_code == 200
    data = r.json()
    assert "total_signals" in data


# ──────────────────────────────────────────────────────────────────────────────
# 8. POST /scan/ais-gaps — AIS gap scan
# ──────────────────────────────────────────────────────────────────────────────


def test_scan_ais_gaps_returns_list(app_client: TestClient):
    """Scan with no telemetry data must return an empty list (not error)."""
    r = app_client.post(f"{BASE}/scan/ais-gaps")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_scan_ais_gaps_custom_threshold(app_client: TestClient):
    r = app_client.post(f"{BASE}/scan/ais-gaps?min_gap_seconds=3600&confidence_threshold=0.6")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
