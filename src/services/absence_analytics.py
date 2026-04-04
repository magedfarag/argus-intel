"""Absence-As-Signal analytics service — Phase 5 Track D.

Follows the same pattern as src/services/event_store.py:
  - class-based store with threading.Lock
  - module-level singleton via get_default_absence_service()
  - deterministic synthetic demo signals seeded on first init

detect_ais_gaps() is a synchronous scan function (not a background poller).
generate_alerts() groups active high-severity signals by entity within a
6-hour window to avoid alert fatigue.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src.models.absence_signals import (
    AbsenceAlert,
    AbsenceAnalyticsSummary,
    AbsenceSeverity,
    AbsenceSignal,
    AbsenceSignalCreateRequest,
    AbsenceSignalType,
)

# Reference date kept in sync with main.py TODAY = date(2026, 3, 28)
_TODAY = datetime(2026, 3, 28, tzinfo=timezone.utc)

# Severity ordering used for comparisons
_SEVERITY_ORDER: Dict[AbsenceSeverity, int] = {
    AbsenceSeverity.LOW: 0,
    AbsenceSeverity.MEDIUM: 1,
    AbsenceSeverity.HIGH: 2,
    AbsenceSeverity.CRITICAL: 3,
}

# ── Synthetic demo absence signals ─────────────────────────────────────────────
# Five deterministic signals covering different types and severities.
# They all use _TODAY as the reference so temporal logic stays relative.

_DEMO_SIGNALS: List[dict] = [
    {
        "signal_type": AbsenceSignalType.AIS_GAP,
        "entity_id": "MMSI-244820000",
        "entity_type": "vessel",
        "gap_start": _TODAY - timedelta(hours=8),
        "gap_end": None,
        "expected_interval_seconds": 120.0,
        "severity": AbsenceSeverity.HIGH,
        "confidence": 0.85,
        "detection_method": "gap_detection",
        "provenance": {
            "source": "aisstream-stub",
            "detection_timestamp": (_TODAY - timedelta(hours=8)).isoformat(),
        },
        "notes": "Cargo vessel MMSI-244820000 silent for 8h entering Black Sea.",
    },
    {
        "signal_type": AbsenceSignalType.GPS_DENIAL,
        "entity_id": None,
        "entity_type": "area",
        "aoi_geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [33.0, 44.5],
                    [34.0, 44.5],
                    [34.0, 45.5],
                    [33.0, 45.5],
                    [33.0, 44.5],
                ]
            ],
        },
        "gap_start": _TODAY - timedelta(days=2),
        "gap_end": _TODAY - timedelta(hours=12),
        "expected_interval_seconds": None,
        "severity": AbsenceSeverity.CRITICAL,
        "confidence": 0.90,
        "detection_method": "feed_monitor",
        "provenance": {
            "source": "gnss-monitor-derived",
            "detection_timestamp": (_TODAY - timedelta(days=2)).isoformat(),
        },
        "notes": "GPS denial event in Black Sea / Crimea vicinity — resolved.",
    },
    {
        "signal_type": AbsenceSignalType.CAMERA_SILENCE,
        "entity_id": "CAM-PORT-ODESSA-01",
        "entity_type": "camera",
        "gap_start": _TODAY - timedelta(hours=3),
        "gap_end": None,
        "expected_interval_seconds": 30.0,
        "severity": AbsenceSeverity.MEDIUM,
        "confidence": 0.75,
        "detection_method": "feed_monitor",
        "provenance": {
            "source": "camera-feed-stub",
            "detection_timestamp": (_TODAY - timedelta(hours=3)).isoformat(),
        },
        "notes": "Port surveillance camera offline.",
    },
    {
        "signal_type": AbsenceSignalType.EXPECTED_MISSING,
        "entity_id": "CALLSIGN-UAL432",
        "entity_type": "aircraft",
        "gap_start": _TODAY - timedelta(hours=6),
        "gap_end": _TODAY - timedelta(hours=4),
        "expected_interval_seconds": 10.0,
        "severity": AbsenceSeverity.LOW,
        "confidence": 0.60,
        "detection_method": "schedule_miss",
        "provenance": {
            "source": "opensky-stub",
            "detection_timestamp": (_TODAY - timedelta(hours=6)).isoformat(),
        },
        "notes": "Aircraft missed scheduled position report — recovered.",
    },
    {
        "signal_type": AbsenceSignalType.COMM_BLACKOUT,
        "entity_id": None,
        "entity_type": "area",
        "aoi_geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [20.0, 54.0],
                    [21.0, 54.0],
                    [21.0, 55.0],
                    [20.0, 55.0],
                    [20.0, 54.0],
                ]
            ],
        },
        "gap_start": _TODAY - timedelta(hours=1),
        "gap_end": None,
        "expected_interval_seconds": None,
        "severity": AbsenceSeverity.HIGH,
        "confidence": 0.80,
        "detection_method": "gap_detection",
        "provenance": {
            "source": "comms-monitor-stub",
            "detection_timestamp": (_TODAY - timedelta(hours=1)).isoformat(),
        },
        "notes": "Baltic Kaliningrad area communications blackout — ongoing.",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────


class AbsenceAnalyticsService:
    """Thread-safe in-memory store and analytics engine for absence signals."""

    def __init__(self) -> None:
        self._signals: Dict[str, AbsenceSignal] = {}
        self._lock = threading.Lock()
        self._seed_demo_signals()

    # ── Seeding ────────────────────────────────────────────────────────────────

    def _seed_demo_signals(self) -> None:
        """Inject deterministic synthetic absence signals for demo/replay purposes."""
        for spec in _DEMO_SIGNALS:
            signal = AbsenceSignal(
                signal_type=spec["signal_type"],
                entity_id=spec.get("entity_id"),
                entity_type=spec.get("entity_type"),
                aoi_geometry=spec.get("aoi_geometry"),
                gap_start=spec["gap_start"],
                gap_end=spec.get("gap_end"),
                expected_interval_seconds=spec.get("expected_interval_seconds"),
                severity=spec["severity"],
                confidence=spec["confidence"],
                detection_method=spec["detection_method"],
                provenance=spec["provenance"],
                notes=spec.get("notes"),
                resolved=spec.get("gap_end") is not None,
            )
            self._signals[signal.signal_id] = signal

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def create_signal(self, req: AbsenceSignalCreateRequest) -> AbsenceSignal:
        """Persist a new absence signal from a create request."""
        signal = AbsenceSignal(
            signal_type=req.signal_type,
            entity_id=req.entity_id,
            entity_type=req.entity_type,
            aoi_geometry=req.aoi_geometry,
            gap_start=req.gap_start,
            gap_end=req.gap_end,
            expected_interval_seconds=req.expected_interval_seconds,
            severity=req.severity,
            confidence=req.confidence,
            detection_method=req.detection_method,
            provenance=req.provenance,
            notes=req.notes,
            resolved=req.gap_end is not None,
        )
        with self._lock:
            self._signals[signal.signal_id] = signal
        return signal

    def get_signal(self, signal_id: str) -> Optional[AbsenceSignal]:
        """Return a single signal by ID, or None if not found."""
        with self._lock:
            return self._signals.get(signal_id)

    def list_signals(
        self,
        signal_type: Optional[AbsenceSignalType] = None,
        entity_id: Optional[str] = None,
        active_only: bool = False,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[AbsenceSignal]:
        """Return signals matching the given filters, newest gap_start first."""
        with self._lock:
            candidates = list(self._signals.values())

        if signal_type is not None:
            candidates = [s for s in candidates if s.signal_type == signal_type]
        if entity_id is not None:
            candidates = [s for s in candidates if s.entity_id == entity_id]
        if active_only:
            candidates = [s for s in candidates if s.gap_end is None]
        if min_confidence > 0.0:
            candidates = [s for s in candidates if s.confidence >= min_confidence]

        candidates.sort(key=lambda s: s.gap_start, reverse=True)
        return candidates[:limit]

    def resolve_signal(self, signal_id: str, gap_end: datetime) -> Optional[AbsenceSignal]:
        """Mark an absence signal as resolved by setting its gap_end timestamp."""
        with self._lock:
            signal = self._signals.get(signal_id)
            if signal is None:
                return None
            updated = signal.model_copy(update={"gap_end": gap_end, "resolved": True})
            self._signals[signal_id] = updated
            return updated

    def link_event(self, signal_id: str, event_id: str) -> Optional[AbsenceSignal]:
        """Link a canonical event ID to an absence signal (idempotent)."""
        with self._lock:
            signal = self._signals.get(signal_id)
            if signal is None:
                return None
            if event_id in signal.related_event_ids:
                return signal
            new_ids = list(signal.related_event_ids) + [event_id]
            updated = signal.model_copy(update={"related_event_ids": new_ids})
            self._signals[signal_id] = updated
            return updated

    def clear(self) -> None:
        """Remove all signals — used in tests."""
        with self._lock:
            self._signals.clear()

    # ── Analytics ──────────────────────────────────────────────────────────────

    def detect_ais_gaps(
        self,
        telemetry_store,
        min_gap_seconds: float = 1800.0,
        confidence_threshold: float = 0.5,
    ) -> List[AbsenceSignal]:
        """Scan TelemetryStore for vessels with AIS gaps > min_gap_seconds.

        For each entity, compares the last known position timestamp to
        datetime.now(timezone.utc).  If the gap exceeds the threshold, an
        AbsenceSignal of type AIS_GAP is created (duplicate entities that
        already have an active AIS_GAP signal are skipped).

        This is a deterministic scan function, not a background poller.
        Returns newly created signals.
        """
        now = datetime.now(timezone.utc)
        new_signals: List[AbsenceSignal] = []

        # Collect entity IDs already tracked as active AIS gaps
        with self._lock:
            tracked_entities = {
                s.entity_id
                for s in self._signals.values()
                if s.signal_type == AbsenceSignalType.AIS_GAP
                and s.gap_end is None
                and s.entity_id is not None
            }

        # Wide query window to find the last known position for each entity
        window_start = now - timedelta(days=30)
        for entity_id in telemetry_store.get_entity_ids():
            if entity_id in tracked_entities:
                continue

            positions = telemetry_store.query_entity(
                entity_id,
                start_time=window_start,
                end_time=now,
                max_points=1,
            )
            # query_entity returns ASC; with max_points=1 we get only the first
            # within the window.  We want the LAST, so query with full default
            # and take the final element.
            positions_full = telemetry_store.query_entity(
                entity_id,
                start_time=window_start,
                end_time=now,
            )
            if not positions_full:
                continue

            last_event = positions_full[-1]
            gap_seconds = (now - last_event.event_time).total_seconds()

            if gap_seconds < min_gap_seconds:
                continue

            # Scale confidence: longer gap → higher confidence up to a cap
            raw_confidence = min(1.0, gap_seconds / (min_gap_seconds * 4))
            if raw_confidence < confidence_threshold:
                continue

            severity = (
                AbsenceSeverity.CRITICAL
                if gap_seconds > min_gap_seconds * 8
                else AbsenceSeverity.HIGH
                if gap_seconds > min_gap_seconds * 4
                else AbsenceSeverity.MEDIUM
            )

            signal = AbsenceSignal(
                signal_type=AbsenceSignalType.AIS_GAP,
                entity_id=entity_id,
                entity_type="vessel",
                gap_start=last_event.event_time,
                gap_end=None,
                expected_interval_seconds=120.0,
                last_known_value={
                    "event_id": last_event.event_id,
                    "source": last_event.source,
                    "event_time": last_event.event_time.isoformat(),
                },
                severity=severity,
                confidence=round(raw_confidence, 3),
                detection_method="gap_detection",
                provenance={
                    "source": last_event.source,
                    "detection_timestamp": now.isoformat(),
                    "gap_seconds": round(gap_seconds, 1),
                },
            )
            with self._lock:
                self._signals[signal.signal_id] = signal
            new_signals.append(signal)

        return new_signals

    def get_summary(
        self, window_start: datetime, window_end: datetime
    ) -> AbsenceAnalyticsSummary:
        """Return aggregated analytics for signals whose gap_start falls in the window."""
        with self._lock:
            candidates = [
                s
                for s in self._signals.values()
                if window_start <= s.gap_start <= window_end
            ]

        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        active = resolved = high_conf = 0

        for s in candidates:
            by_type[s.signal_type.value] = by_type.get(s.signal_type.value, 0) + 1
            by_severity[s.severity.value] = by_severity.get(s.severity.value, 0) + 1
            if s.gap_end is None:
                active += 1
            else:
                resolved += 1
            if s.confidence >= 0.7:
                high_conf += 1

        return AbsenceAnalyticsSummary(
            window_start=window_start,
            window_end=window_end,
            total_signals=len(candidates),
            by_type=by_type,
            by_severity=by_severity,
            active_signals=active,
            resolved_signals=resolved,
            high_confidence_count=high_conf,
        )

    def generate_alerts(
        self, min_severity: AbsenceSeverity = AbsenceSeverity.MEDIUM
    ) -> List[AbsenceAlert]:
        """Group active high-severity signals into alerts.

        One alert per cluster of co-located signals (same entity_id or same
        area_description) within a 6-hour window.  Signals below min_severity
        are excluded.
        """
        min_rank = _SEVERITY_ORDER[min_severity]
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=6)

        with self._lock:
            candidates = [
                s
                for s in self._signals.values()
                if s.gap_end is None
                and _SEVERITY_ORDER[s.severity] >= min_rank
                and s.gap_start >= cutoff
            ]

        # Group by entity_id (or signal_type for area signals without an entity)
        clusters: Dict[str, List[AbsenceSignal]] = {}
        for s in candidates:
            key = s.entity_id if s.entity_id else f"area:{s.signal_type.value}"
            clusters.setdefault(key, []).append(s)

        alerts: List[AbsenceAlert] = []
        for key, signals in clusters.items():
            if not signals:
                continue
            max_sev = max(signals, key=lambda s: _SEVERITY_ORDER[s.severity]).severity
            avg_conf = sum(s.confidence for s in signals) / len(signals)
            title = (
                f"AIS gap detected for {key}"
                if signals[0].signal_type == AbsenceSignalType.AIS_GAP
                else f"Absence alert: {signals[0].signal_type.value} [{key}]"
            )
            area_desc = key if not signals[0].entity_id else None
            alerts.append(
                AbsenceAlert(
                    title=title,
                    signals=[s.signal_id for s in signals],
                    severity=max_sev,
                    area_description=area_desc,
                    confidence=round(avg_conf, 3),
                    suggested_actions=[
                        "Cross-reference with nearby vessel traffic",
                        "Check for GPS jamming or spoofing in the area",
                        "Alert tasking authority for optical revisit",
                    ],
                )
            )

        return alerts


# ──────────────────────────────────────────────────────────────────────────────
# Process-wide singleton
# ──────────────────────────────────────────────────────────────────────────────

_default_service: Optional[AbsenceAnalyticsService] = None
_default_service_lock = threading.Lock()


def get_default_absence_service() -> AbsenceAnalyticsService:
    """Return the process-wide AbsenceAnalyticsService singleton."""
    global _default_service
    with _default_service_lock:
        if _default_service is None:
            _default_service = AbsenceAnalyticsService()
    return _default_service
