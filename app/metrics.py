"""In-process metrics registry for ARGUS — Phase 6 Track C.

Provides thread-safe counters, gauges, and histograms without requiring
prometheus_client.  The registry serialises to JSON for the
GET /api/v1/health/metrics endpoint.

If prometheus_client is added in a future release, migrate by replacing
this module with thin wrappers around prom Counter/Gauge/Histogram objects.

Metric families tracked
-----------------------
  ingestion_lag_seconds         — histogram (per source_family label)
  replay_query_duration_seconds — histogram
  connector_last_fetch_timestamp — gauge (per connector label)
  connector_error_count          — counter (per connector label)
  active_investigations_total    — gauge
  evidence_pack_exports_total    — counter
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

# ── Module-level state (replaced in tests via reset_all) ──────────────────────

_lock = threading.Lock()

_counters: Dict[str, float] = {}
_gauges: Dict[str, float] = {}
_histograms: Dict[str, List[float]] = {}

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_key(name: str, labels: Optional[Dict[str, str]] = None) -> str:
    """Build a unique metric key from name + optional label map."""
    if not labels:
        return name
    label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}}"


# ── Primitive operations ───────────────────────────────────────────────────────


def increment(
    name: str,
    value: float = 1.0,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Increment a named counter by *value* (thread-safe)."""
    key = _make_key(name, labels)
    with _lock:
        _counters[key] = _counters.get(key, 0.0) + value


def set_gauge(
    name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Set a named gauge to *value* (thread-safe)."""
    key = _make_key(name, labels)
    with _lock:
        _gauges[key] = value


def observe(
    name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Record a single histogram observation (thread-safe)."""
    key = _make_key(name, labels)
    with _lock:
        if key not in _histograms:
            _histograms[key] = []
        _histograms[key].append(value)


# ── Domain helpers ─────────────────────────────────────────────────────────────


def record_ingestion_lag(source_family: str, lag_seconds: float) -> None:
    """Record time from event timestamp to store insertion for a source family."""
    observe("ingestion_lag_seconds", lag_seconds, {"source_family": source_family})


def record_replay_query_duration(duration_seconds: float) -> None:
    """Record a replay / historical query duration in seconds."""
    observe("replay_query_duration_seconds", duration_seconds)


def set_connector_last_fetch(connector_id: str, timestamp: float) -> None:
    """Set the last-successful-fetch Unix timestamp for a connector."""
    set_gauge(
        "connector_last_fetch_timestamp",
        timestamp,
        {"connector": connector_id},
    )


def record_connector_error(connector_id: str) -> None:
    """Increment the per-connector error counter."""
    increment("connector_error_count", labels={"connector": connector_id})


def set_active_investigations(count: int) -> None:
    """Set the active investigations gauge."""
    set_gauge("active_investigations_total", float(count))


def increment_evidence_pack_exports(value: float = 1.0) -> None:
    """Increment the evidence pack exports counter."""
    increment("evidence_pack_exports_total", value)


# ── Read / serialise ───────────────────────────────────────────────────────────


def _percentile(samples: List[float], pct: float) -> Optional[float]:
    """Return the *pct*-th percentile from a list of samples."""
    if not samples:
        return None
    sorted_s = sorted(samples)
    idx = min(int(len(sorted_s) * pct / 100.0), len(sorted_s) - 1)
    return sorted_s[idx]


def snapshot() -> Dict[str, Any]:
    """Return a point-in-time snapshot of all metrics as a JSON-serialisable dict."""
    with _lock:
        counters_copy = dict(_counters)
        gauges_copy = dict(_gauges)
        histograms_copy = {
            k: {
                "count": len(v),
                "sum": sum(v),
                "p50": _percentile(v, 50),
                "p95": _percentile(v, 95),
                "p99": _percentile(v, 99),
            }
            for k, v in _histograms.items()
        }
    return {
        "counters": counters_copy,
        "gauges": gauges_copy,
        "histograms": histograms_copy,
        "snapshot_at": time.time(),
    }


def get_counter(name: str, labels: Optional[Dict[str, str]] = None) -> float:
    """Return the current value of a counter (0.0 if not yet set)."""
    key = _make_key(name, labels)
    with _lock:
        return _counters.get(key, 0.0)


def get_gauge(name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
    """Return the current value of a gauge (None if not yet set)."""
    key = _make_key(name, labels)
    with _lock:
        return _gauges.get(key)


def reset_all() -> None:
    """Clear all metrics state.  Used in tests to isolate test cases."""
    with _lock:
        _counters.clear()
        _gauges.clear()
        _histograms.clear()
