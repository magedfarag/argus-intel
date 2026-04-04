"""Unit tests for app/metrics.py — Phase 6 Track C.

All tests call reset_all() via the autouse fixture to ensure isolation.
"""
from __future__ import annotations

import threading
import time

import pytest

from app import metrics


@pytest.fixture(autouse=True)
def _clean_metrics():
    """Reset all metrics state before every test."""
    metrics.reset_all()
    yield
    metrics.reset_all()


# ── Counter tests ──────────────────────────────────────────────────────────────


def test_increment_starts_at_zero():
    assert metrics.get_counter("my_counter") == 0.0


def test_increment_once():
    metrics.increment("my_counter")
    assert metrics.get_counter("my_counter") == 1.0


def test_increment_with_custom_value():
    metrics.increment("my_counter", 5.0)
    assert metrics.get_counter("my_counter") == 5.0


def test_increment_accumulates():
    metrics.increment("my_counter", 3.0)
    metrics.increment("my_counter", 4.0)
    assert metrics.get_counter("my_counter") == 7.0


def test_increment_with_labels():
    metrics.increment("req_total", labels={"method": "GET"})
    metrics.increment("req_total", labels={"method": "POST"})
    assert metrics.get_counter("req_total", {"method": "GET"}) == 1.0
    assert metrics.get_counter("req_total", {"method": "POST"}) == 1.0


def test_increment_evidence_pack_exports():
    metrics.increment_evidence_pack_exports()
    metrics.increment_evidence_pack_exports()
    assert metrics.get_counter("evidence_pack_exports_total") == 2.0


def test_record_connector_error():
    metrics.record_connector_error("gdelt-doc")
    metrics.record_connector_error("gdelt-doc")
    metrics.record_connector_error("opensky")
    assert metrics.get_counter("connector_error_count", {"connector": "gdelt-doc"}) == 2.0
    assert metrics.get_counter("connector_error_count", {"connector": "opensky"}) == 1.0


# ── Gauge tests ────────────────────────────────────────────────────────────────


def test_set_gauge_returns_correct_value():
    metrics.set_gauge("my_gauge", 42.0)
    assert metrics.get_gauge("my_gauge") == 42.0


def test_set_gauge_overwrites():
    metrics.set_gauge("my_gauge", 10.0)
    metrics.set_gauge("my_gauge", 20.0)
    assert metrics.get_gauge("my_gauge") == 20.0


def test_get_gauge_returns_none_when_unset():
    assert metrics.get_gauge("nonexistent_gauge") is None


def test_set_active_investigations():
    metrics.set_active_investigations(7)
    assert metrics.get_gauge("active_investigations_total") == 7.0


def test_set_connector_last_fetch():
    ts = time.time()
    metrics.set_connector_last_fetch("ais-stream", ts)
    assert metrics.get_gauge("connector_last_fetch_timestamp", {"connector": "ais-stream"}) == ts


# ── Histogram tests ────────────────────────────────────────────────────────────


def test_observe_appears_in_snapshot():
    metrics.observe("my_hist", 1.5)
    snap = metrics.snapshot()
    assert "my_hist" in snap["histograms"]


def test_histogram_count_and_sum():
    metrics.observe("my_hist", 1.0)
    metrics.observe("my_hist", 3.0)
    snap = metrics.snapshot()
    h = snap["histograms"]["my_hist"]
    assert h["count"] == 2
    assert h["sum"] == pytest.approx(4.0)


def test_histogram_percentiles_are_ordered():
    for v in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
        metrics.observe("latency", v)
    snap = metrics.snapshot()
    h = snap["latency"] if "latency" in snap else snap["histograms"]["latency"]
    assert h["p50"] <= h["p95"] <= h["p99"]


def test_record_ingestion_lag():
    metrics.record_ingestion_lag("ais", 12.5)
    snap = metrics.snapshot()
    key = "ingestion_lag_seconds{source_family=ais}"
    assert key in snap["histograms"]
    assert snap["histograms"][key]["count"] == 1


def test_record_replay_query_duration():
    metrics.record_replay_query_duration(0.8)
    snap = metrics.snapshot()
    assert "replay_query_duration_seconds" in snap["histograms"]


# ── Snapshot structure tests ───────────────────────────────────────────────────


def test_snapshot_has_required_sections():
    snap = metrics.snapshot()
    for section in ("counters", "gauges", "histograms", "snapshot_at"):
        assert section in snap


def test_snapshot_at_is_float():
    snap = metrics.snapshot()
    assert isinstance(snap["snapshot_at"], float)


def test_snapshot_is_stable_after_reset():
    metrics.increment("x")
    metrics.reset_all()
    snap = metrics.snapshot()
    assert snap["counters"] == {}
    assert snap["gauges"] == {}
    assert snap["histograms"] == {}


# ── Thread-safety ──────────────────────────────────────────────────────────────


def test_concurrent_increments_are_thread_safe():
    n_threads = 20
    n_per_thread = 50

    def _increment():
        for _ in range(n_per_thread):
            metrics.increment("thread_counter")

    threads = [threading.Thread(target=_increment) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert metrics.get_counter("thread_counter") == float(n_threads * n_per_thread)
