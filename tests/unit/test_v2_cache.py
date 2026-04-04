"""Unit tests for V2CacheService — P5-1.1 through P5-1.4."""
from __future__ import annotations

import pytest
from app.cache.client import CacheClient
from src.services.v2_cache import V2CacheService, _hash_dict


@pytest.fixture
def cache() -> V2CacheService:
    return V2CacheService(CacheClient(redis_url="", ttl_seconds=60, max_entries=64))


# ── _hash_dict ─────────────────────────────────────────────────────────────────

def test_hash_dict_stable():
    """Same dict always yields same hash."""
    h1 = _hash_dict({"a": "Riyadh", "b": 7})
    h2 = _hash_dict({"a": "Riyadh", "b": 7})
    assert h1 == h2


def test_hash_dict_different_on_different_input():
    h1 = _hash_dict({"a": "Riyadh"})
    h2 = _hash_dict({"a": "Dubai"})
    assert h1 != h2


def test_hash_dict_key_order_independent():
    """Sort-key ensures different dict orderings hash identically."""
    h1 = _hash_dict({"a": 1, "b": 2})
    h2 = _hash_dict({"b": 2, "a": 1})
    assert h1 == h2


def test_hash_dict_returns_16_chars():
    assert len(_hash_dict({"x": "y"})) == 16


# ── Timeline caching (P5-1.1) ──────────────────────────────────────────────────

def test_timeline_cache_miss_returns_none(cache: V2CacheService):
    assert cache.get_timeline(None, "2026-01-01", "2026-01-31", 60) is None


def test_timeline_cache_round_trip(cache: V2CacheService):
    value = {"buckets": [{"time": "2026-01-01T00:00:00Z", "count": 5}]}
    cache.set_timeline("aoi-1", "2026-01-01", "2026-01-31", 60, value)
    result = cache.get_timeline("aoi-1", "2026-01-01", "2026-01-31", 60)
    assert result == value


def test_timeline_cache_different_params_different_keys(cache: V2CacheService):
    v1 = {"buckets": [{"count": 1}]}
    v2 = {"buckets": [{"count": 2}]}
    cache.set_timeline("aoi-a", "2026-01-01", "2026-01-31", 60, v1)
    cache.set_timeline("aoi-b", "2026-01-01", "2026-01-31", 60, v2)
    assert cache.get_timeline("aoi-a", "2026-01-01", "2026-01-31", 60) == v1
    assert cache.get_timeline("aoi-b", "2026-01-01", "2026-01-31", 60) == v2


# ── STAC search caching (P5-1.2) ───────────────────────────────────────────────

def test_stac_cache_miss_returns_none(cache: V2CacheService):
    assert cache.get_stac_search({"start": "2026-01-01", "end": "2026-01-31"}) is None


def test_stac_cache_round_trip(cache: V2CacheService):
    params = {"aoi": "test", "start": "2026-01-01", "end": "2026-01-31", "cloud": 20}
    value = {"items": [{"item_id": "S2A_1234"}]}
    cache.set_stac_search(params, value)
    assert cache.get_stac_search(params) == value


# ── Playback caching (P5-1.3) ──────────────────────────────────────────────────

def test_playback_cache_miss_returns_none(cache: V2CacheService):
    assert cache.get_playback({"aoi_id": "x", "start": "2026-01-01"}) is None


def test_playback_cache_round_trip(cache: V2CacheService):
    params = {"aoi_id": "aoi-1", "start": "2026-01-01T00:00:00Z", "end": "2026-01-07T00:00:00Z"}
    value = {"frames": [{"sequence": 1, "event_id": "evt-1"}], "total": 1}
    cache.set_playback(params, value)
    assert cache.get_playback(params) == value


# ── Source health caching (P5-1.4) ────────────────────────────────────────────

def test_source_health_miss_returns_none(cache: V2CacheService):
    assert cache.get_source_health("gdelt") is None


def test_source_health_round_trip(cache: V2CacheService):
    snap = {"connector_id": "gdelt", "is_healthy": True}
    cache.set_source_health("gdelt", snap)
    assert cache.get_source_health("gdelt") == snap


def test_all_source_health_round_trip(cache: V2CacheService):
    snap = {"connectors": [{"id": "earth-search", "healthy": True}]}
    cache.set_all_source_health(snap)
    assert cache.get_all_source_health() == snap


def test_invalidate_source_health_clears_all(cache: V2CacheService):
    cache.set_source_health("gdelt", {"x": 1})
    cache.set_all_source_health({"all": True})
    cache.invalidate_source_health()
    assert cache.get_all_source_health() is None


def test_stats_track_hits_and_misses(cache: V2CacheService):
    cache.get_timeline(None, "a", "b", 60)  # miss
    cache.set_timeline(None, "a", "b", 60, {"buckets": []})
    cache.get_timeline(None, "a", "b", 60)  # hit
    stats = cache.stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
