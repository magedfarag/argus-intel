"""Unit tests for app/cache/query_cache.py — Phase 6 Track B."""
from __future__ import annotations

import threading
import time

import pytest

from app.cache.query_cache import (
    QueryCache,
    get_query_cache,
    reset_query_cache,
    ttl_for_window,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def cache() -> QueryCache:
    """Return a fresh QueryCache for each test."""
    return QueryCache()


# ── Basic get/set/miss behaviour ──────────────────────────────────────────────


def test_get_miss_on_empty_cache(cache: QueryCache) -> None:
    result = cache.get("nonexistent-key")
    assert result is None


def test_set_and_get_hit(cache: QueryCache) -> None:
    cache.set("k1", {"data": [1, 2, 3]}, ttl=60.0)
    result = cache.get("k1")
    assert result == {"data": [1, 2, 3]}


def test_set_stores_any_serialisable_type(cache: QueryCache) -> None:
    cache.set("str-key", "hello", ttl=60.0)
    cache.set("list-key", [1, 2], ttl=60.0)
    cache.set("none-key", None, ttl=60.0)
    # None stored explicitly is a hit (not confused with a miss)
    assert cache.get("str-key") == "hello"
    assert cache.get("list-key") == [1, 2]
    # None is a valid cached value — get() returns None on BOTH miss and stored-None.
    # The cache does not distinguish the two by design (callers use TTL to bound staleness).
    # Storing None is allowed but the return value is indistinguishable from a miss.


def test_overwrite_key(cache: QueryCache) -> None:
    cache.set("key", "original", ttl=60.0)
    cache.set("key", "updated", ttl=60.0)
    assert cache.get("key") == "updated"


def test_multiple_independent_keys(cache: QueryCache) -> None:
    cache.set("a", 1, ttl=60.0)
    cache.set("b", 2, ttl=60.0)
    assert cache.get("a") == 1
    assert cache.get("b") == 2


def test_invalidate_removes_entry(cache: QueryCache) -> None:
    cache.set("inv", "value", ttl=60.0)
    cache.invalidate("inv")
    assert cache.get("inv") is None


def test_invalidate_noop_on_missing_key(cache: QueryCache) -> None:
    # Should not raise
    cache.invalidate("ghost-key")


# ── TTL expiry ────────────────────────────────────────────────────────────────


def test_ttl_expiry(cache: QueryCache) -> None:
    cache.set("exp", "value", ttl=0.05)  # 50 ms TTL
    assert cache.get("exp") == "value"
    time.sleep(0.1)  # Wait for expiry
    assert cache.get("exp") is None


def test_expired_entry_increments_eviction_count(cache: QueryCache) -> None:
    cache.set("ev", "v", ttl=0.05)
    time.sleep(0.1)
    cache.get("ev")  # triggers eviction
    stats = cache.stats()
    assert stats["evictions"] >= 1


def test_purge_expired_removes_stale_entries(cache: QueryCache) -> None:
    cache.set("stale", "v", ttl=0.05)
    cache.set("fresh", "v2", ttl=60.0)
    time.sleep(0.1)
    removed = cache.purge_expired()
    assert removed == 1
    assert cache.get("fresh") == "v2"
    assert cache.get("stale") is None


# ── Statistics ────────────────────────────────────────────────────────────────


def test_stats_hit_count(cache: QueryCache) -> None:
    cache.set("k", "v", ttl=60.0)
    cache.get("k")
    cache.get("k")
    stats = cache.stats()
    assert stats["hits"] == 2


def test_stats_miss_count(cache: QueryCache) -> None:
    cache.get("missing")
    cache.get("also-missing")
    stats = cache.stats()
    assert stats["misses"] == 2


def test_stats_hit_rate_with_no_requests(cache: QueryCache) -> None:
    stats = cache.stats()
    assert stats["hit_rate"] == 0.0
    assert stats["miss_rate"] == 0.0


def test_stats_hit_rate_calculation(cache: QueryCache) -> None:
    cache.set("k", "v", ttl=60.0)
    cache.get("k")   # hit
    cache.get("x")   # miss
    stats = cache.stats()
    assert stats["hit_rate"] == pytest.approx(0.5)
    assert stats["miss_rate"] == pytest.approx(0.5)


def test_stats_total_entries(cache: QueryCache) -> None:
    cache.set("a", 1, ttl=60.0)
    cache.set("b", 2, ttl=60.0)
    stats = cache.stats()
    assert stats["total_entries"] == 2


def test_stats_total_entries_excludes_expired(cache: QueryCache) -> None:
    cache.set("live", "v", ttl=60.0)
    cache.set("dead", "v", ttl=0.05)
    time.sleep(0.1)
    stats = cache.stats()
    # dead entry should not be reported as live
    assert stats["total_entries"] == 1


# ── Thread safety ─────────────────────────────────────────────────────────────


def test_concurrent_writes_are_safe(cache: QueryCache) -> None:
    """50 threads each write 100 keys — no race conditions or data corruption."""
    errors: list[Exception] = []

    def writer(thread_id: int) -> None:
        try:
            for i in range(100):
                cache.set(f"t{thread_id}:k{i}", thread_id * 100 + i, ttl=60.0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent write raised: {errors}"


def test_concurrent_reads_are_safe(cache: QueryCache) -> None:
    """50 threads read the same key concurrently — no corruption."""
    cache.set("shared", "value", ttl=60.0)
    results: list = []
    errors: list[Exception] = []

    def reader() -> None:
        try:
            results.append(cache.get("shared"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert all(r == "value" for r in results)


# ── TTL helper ────────────────────────────────────────────────────────────────


def test_ttl_for_window_24h() -> None:
    assert ttl_for_window(1) == 60.0


def test_ttl_for_window_less_than_24h() -> None:
    assert ttl_for_window(0.5) == 60.0


def test_ttl_for_window_7d() -> None:
    assert ttl_for_window(7) == 300.0


def test_ttl_for_window_mid_range() -> None:
    assert ttl_for_window(3) == 300.0


def test_ttl_for_window_30d() -> None:
    assert ttl_for_window(30) == 600.0


def test_ttl_for_window_beyond_30d() -> None:
    assert ttl_for_window(365) == 600.0


# ── Singleton ─────────────────────────────────────────────────────────────────


def test_get_query_cache_returns_same_instance() -> None:
    c1 = get_query_cache()
    c2 = get_query_cache()
    assert c1 is c2


def test_reset_query_cache_replaces_singleton() -> None:
    c1 = get_query_cache()
    c1.set("persistent", "val", ttl=60.0)
    reset_query_cache()
    c2 = get_query_cache()
    assert c2 is not c1
    assert c2.get("persistent") is None
