"""Unit tests for Absence-As-Signal models and service — Phase 5 Track D.

Tests cover:
  - Model construction and validation
  - Enum values
  - UTC datetime enforcement
  - Confidence bound enforcement
  - Service CRUD operations
  - Analytics methods
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from src.models.absence_signals import (
    AbsenceAlert,
    AbsenceAnalyticsSummary,
    AbsenceSeverity,
    AbsenceSignal,
    AbsenceSignalCreateRequest,
    AbsenceSignalType,
)
from src.services.absence_analytics import AbsenceAnalyticsService


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _make_req(**overrides) -> AbsenceSignalCreateRequest:
    defaults = dict(
        signal_type=AbsenceSignalType.AIS_GAP,
        entity_id="MMSI-123456789",
        entity_type="vessel",
        gap_start=_NOW - timedelta(hours=2),
        severity=AbsenceSeverity.HIGH,
        confidence=0.8,
        detection_method="gap_detection",
        provenance={"source": "aisstream", "detection_timestamp": _NOW.isoformat()},
    )
    defaults.update(overrides)
    return AbsenceSignalCreateRequest(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# 1. AbsenceSignalType enum values
# ──────────────────────────────────────────────────────────────────────────────


def test_signal_type_values():
    assert AbsenceSignalType.AIS_GAP == "ais_gap"
    assert AbsenceSignalType.GPS_DENIAL == "gps_denial"
    assert AbsenceSignalType.CAMERA_SILENCE == "camera_silence"
    assert AbsenceSignalType.EXPECTED_MISSING == "expected_missing"
    assert AbsenceSignalType.COMM_BLACKOUT == "comm_blackout"
    assert AbsenceSignalType.TRACK_TERMINATION == "track_termination"


# ──────────────────────────────────────────────────────────────────────────────
# 2. AbsenceSeverity enum values
# ──────────────────────────────────────────────────────────────────────────────


def test_severity_values():
    assert AbsenceSeverity.LOW == "low"
    assert AbsenceSeverity.MEDIUM == "medium"
    assert AbsenceSeverity.HIGH == "high"
    assert AbsenceSeverity.CRITICAL == "critical"


# ──────────────────────────────────────────────────────────────────────────────
# 3. AbsenceSignal model construction
# ──────────────────────────────────────────────────────────────────────────────


def test_absence_signal_full_construction():
    sig = AbsenceSignal(
        signal_type=AbsenceSignalType.AIS_GAP,
        entity_id="MMSI-987654321",
        entity_type="vessel",
        gap_start=_NOW - timedelta(hours=5),
        gap_end=_NOW - timedelta(hours=1),
        expected_interval_seconds=120.0,
        severity=AbsenceSeverity.CRITICAL,
        confidence=0.95,
        detection_method="gap_detection",
        provenance={"source": "demo", "detection_timestamp": _NOW.isoformat()},
        notes="Test note",
        related_event_ids=["evt-001"],
    )
    assert sig.signal_id  # auto-generated UUID
    assert sig.entity_id == "MMSI-987654321"
    assert sig.confidence == 0.95
    assert sig.gap_end == _NOW - timedelta(hours=1)
    assert "evt-001" in sig.related_event_ids


def test_absence_signal_defaults():
    sig = AbsenceSignal(
        signal_type=AbsenceSignalType.GPS_DENIAL,
        gap_start=_NOW,
        severity=AbsenceSeverity.LOW,
        confidence=0.5,
        detection_method="feed_monitor",
        provenance={"source": "demo"},
    )
    assert sig.gap_end is None
    assert sig.resolved is False
    assert sig.related_event_ids == []
    assert sig.entity_id is None


def test_absence_signal_auto_uuid():
    a = AbsenceSignal(
        signal_type=AbsenceSignalType.CAMERA_SILENCE,
        gap_start=_NOW,
        severity=AbsenceSeverity.MEDIUM,
        confidence=0.6,
        detection_method="feed_monitor",
        provenance={},
    )
    b = AbsenceSignal(
        signal_type=AbsenceSignalType.CAMERA_SILENCE,
        gap_start=_NOW,
        severity=AbsenceSeverity.MEDIUM,
        confidence=0.6,
        detection_method="feed_monitor",
        provenance={},
    )
    assert a.signal_id != b.signal_id


# ──────────────────────────────────────────────────────────────────────────────
# 4. Confidence bounds enforcement
# ──────────────────────────────────────────────────────────────────────────────


def test_confidence_below_zero_rejected():
    with pytest.raises(Exception):
        AbsenceSignal(
            signal_type=AbsenceSignalType.AIS_GAP,
            gap_start=_NOW,
            severity=AbsenceSeverity.HIGH,
            confidence=-0.1,
            detection_method="gap_detection",
            provenance={},
        )


def test_confidence_above_one_rejected():
    with pytest.raises(Exception):
        AbsenceSignal(
            signal_type=AbsenceSignalType.AIS_GAP,
            gap_start=_NOW,
            severity=AbsenceSeverity.HIGH,
            confidence=1.1,
            detection_method="gap_detection",
            provenance={},
        )


def test_confidence_boundary_values_accepted():
    for conf in (0.0, 0.5, 1.0):
        sig = AbsenceSignal(
            signal_type=AbsenceSignalType.AIS_GAP,
            gap_start=_NOW,
            severity=AbsenceSeverity.LOW,
            confidence=conf,
            detection_method="gap_detection",
            provenance={},
        )
        assert sig.confidence == conf


# ──────────────────────────────────────────────────────────────────────────────
# 5. UTC datetime enforcement
# ──────────────────────────────────────────────────────────────────────────────


def test_naive_gap_start_rejected():
    with pytest.raises(Exception):
        AbsenceSignal(
            signal_type=AbsenceSignalType.AIS_GAP,
            gap_start=datetime(2026, 3, 28, 10, 0, 0),  # naive — no tzinfo
            severity=AbsenceSeverity.LOW,
            confidence=0.5,
            detection_method="gap_detection",
            provenance={},
        )


def test_z_suffix_accepted():
    sig = AbsenceSignal(
        signal_type=AbsenceSignalType.AIS_GAP,
        gap_start="2026-03-28T10:00:00Z",
        severity=AbsenceSeverity.LOW,
        confidence=0.5,
        detection_method="gap_detection",
        provenance={},
    )
    assert sig.gap_start.tzinfo is not None


# ──────────────────────────────────────────────────────────────────────────────
# 6. Signal with ongoing gap (gap_end=None)
# ──────────────────────────────────────────────────────────────────────────────


def test_ongoing_signal_gap_end_none():
    sig = AbsenceSignal(
        signal_type=AbsenceSignalType.AIS_GAP,
        entity_id="MMSI-111",
        entity_type="vessel",
        gap_start=_NOW - timedelta(hours=10),
        gap_end=None,
        severity=AbsenceSeverity.HIGH,
        confidence=0.9,
        detection_method="gap_detection",
        provenance={},
    )
    assert sig.gap_end is None
    assert sig.resolved is False


# ──────────────────────────────────────────────────────────────────────────────
# 7. AbsenceAnalyticsSummary construction
# ──────────────────────────────────────────────────────────────────────────────


def test_summary_construction():
    summary = AbsenceAnalyticsSummary(
        window_start=_NOW - timedelta(days=1),
        window_end=_NOW,
        total_signals=10,
        by_type={"ais_gap": 5, "gps_denial": 3, "camera_silence": 2},
        by_severity={"high": 4, "critical": 2, "medium": 4},
        active_signals=7,
        resolved_signals=3,
        high_confidence_count=6,
    )
    assert summary.total_signals == 10
    assert summary.by_type["ais_gap"] == 5
    assert summary.active_signals == 7


# ──────────────────────────────────────────────────────────────────────────────
# 8. AbsenceAlert auto-UUID
# ──────────────────────────────────────────────────────────────────────────────


def test_alert_auto_uuid():
    alert = AbsenceAlert(
        title="Test Alert",
        signals=["sig-001"],
        severity=AbsenceSeverity.HIGH,
        confidence=0.8,
    )
    assert alert.alert_id
    assert alert.created_at.tzinfo is not None


# ──────────────────────────────────────────────────────────────────────────────
# 9–19. Service operations
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def svc() -> AbsenceAnalyticsService:
    s = AbsenceAnalyticsService()
    s.clear()
    return s


def test_service_create_signal(svc: AbsenceAnalyticsService):
    req = _make_req()
    sig = svc.create_signal(req)
    assert sig.signal_id
    assert sig.signal_type == AbsenceSignalType.AIS_GAP
    assert sig.entity_id == "MMSI-123456789"


def test_service_get_signal(svc: AbsenceAnalyticsService):
    req = _make_req()
    created = svc.create_signal(req)
    fetched = svc.get_signal(created.signal_id)
    assert fetched is not None
    assert fetched.signal_id == created.signal_id


def test_service_get_missing_returns_none(svc: AbsenceAnalyticsService):
    assert svc.get_signal("nonexistent-id") is None


def test_service_list_signals(svc: AbsenceAnalyticsService):
    svc.create_signal(_make_req(entity_id="MMSI-A"))
    svc.create_signal(_make_req(entity_id="MMSI-B"))
    results = svc.list_signals()
    assert len(results) == 2


def test_service_list_active_only_filter(svc: AbsenceAnalyticsService):
    # active (no gap_end)
    svc.create_signal(_make_req(entity_id="MMSI-ACTIVE"))
    # resolved (gap_end set)
    svc.create_signal(_make_req(entity_id="MMSI-RESOLVED", gap_end=_NOW))
    active = svc.list_signals(active_only=True)
    assert all(s.gap_end is None for s in active)
    assert any(s.entity_id == "MMSI-ACTIVE" for s in active)


def test_service_resolve_signal(svc: AbsenceAnalyticsService):
    sig = svc.create_signal(_make_req())
    resolved = svc.resolve_signal(sig.signal_id, gap_end=_NOW)
    assert resolved is not None
    assert resolved.resolved is True
    assert resolved.gap_end == _NOW


def test_service_resolve_nonexistent_returns_none(svc: AbsenceAnalyticsService):
    assert svc.resolve_signal("no-such-id", _NOW) is None


def test_service_link_event_accumulates(svc: AbsenceAnalyticsService):
    sig = svc.create_signal(_make_req())
    updated1 = svc.link_event(sig.signal_id, "evt-001")
    updated2 = svc.link_event(sig.signal_id, "evt-002")
    assert updated2 is not None
    assert "evt-001" in updated2.related_event_ids
    assert "evt-002" in updated2.related_event_ids


def test_service_link_event_idempotent(svc: AbsenceAnalyticsService):
    sig = svc.create_signal(_make_req())
    svc.link_event(sig.signal_id, "evt-dup")
    svc.link_event(sig.signal_id, "evt-dup")
    final = svc.get_signal(sig.signal_id)
    assert final is not None
    assert final.related_event_ids.count("evt-dup") == 1


def test_service_get_summary_counts(svc: AbsenceAnalyticsService):
    window_start = _NOW - timedelta(hours=24)
    window_end = _NOW + timedelta(hours=1)
    svc.create_signal(_make_req(gap_start=_NOW - timedelta(hours=5), confidence=0.9))
    svc.create_signal(_make_req(gap_start=_NOW - timedelta(hours=3), confidence=0.4, gap_end=_NOW))
    summary = svc.get_summary(window_start=window_start, window_end=window_end)
    assert summary.total_signals == 2
    assert summary.active_signals == 1
    assert summary.resolved_signals == 1
    assert summary.high_confidence_count == 1


def test_service_generate_alerts_excludes_low(svc: AbsenceAnalyticsService):
    # LOW severity ongoing signal — should be excluded from default MEDIUM threshold
    svc.create_signal(_make_req(
        severity=AbsenceSeverity.LOW,
        gap_start=datetime.now(timezone.utc) - timedelta(hours=1),
    ))
    alerts = svc.generate_alerts(min_severity=AbsenceSeverity.MEDIUM)
    assert all(
        alert.severity != AbsenceSeverity.LOW for alert in alerts
    )
