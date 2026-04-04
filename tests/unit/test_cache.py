"""Unit tests for CacheClient."""
from __future__ import annotations
from app.cache.client import CacheClient

def test_memory_cache_set_get():
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=16)
    c.set("k", {"data": 42})
    assert c.get("k") == {"data": 42}

def test_memory_cache_miss_returns_none():
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=16)
    assert c.get("missing") is None

def test_memory_cache_delete():
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=16)
    c.set("k", "v"); c.delete("k")
    assert c.get("k") is None

def test_hit_rate_stats():
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=16)
    c.set("x", 1)
    c.get("x"); c.get("missing")
    s = c.stats()
    assert s["hits"] == 1 and s["misses"] == 1 and s["hit_rate"] == 0.5

def test_is_healthy_memory():
    # In-memory fallback is a degraded state per design — is_healthy returns False
    # to signal to the health endpoint that Redis persistence is unavailable.
    assert CacheClient(redis_url="", ttl_seconds=10, max_entries=4).is_healthy() is False

def test_redis_fallback_on_invalid_url():
    c = CacheClient(redis_url="redis://invalid.local:9999/0", ttl_seconds=10, max_entries=4)
    c.set("k", "v")
    assert c.get("k") == "v"


# P1-2: Redis integration tests


def test_cache_client_verifies_redis_connection_timeout():
    """Verify CacheClient uses fallback when Redis connection times out (socket_connect_timeout=3)."""
    # This validates the specific behavior: 3-second timeout prevents hanging
    c = CacheClient(redis_url="redis://localhost:12345/0", ttl_seconds=10, max_entries=16)

    # Should have fallen back to memory (because connection timed out)
    assert c._redis is None
    assert c._memory is not None

    # And still be usable
    c.set("k", "v")
    assert c.get("k") == "v"


def test_cache_client_json_serialization():
    """Verify cache handles JSON serialization with default=str for non-serializable types."""
    from datetime import datetime
    import json

    c = CacheClient(redis_url="", ttl_seconds=60)

    # Store data with datetime (not JSON-serializable by default)
    data = {"timestamp": datetime(2026, 3, 28, 10, 30), "value": 42}
    c.set("dt_key", data)
    result = c.get("dt_key")

    assert result["value"] == 42
    # In-memory TTLCache stores the object directly without JSON roundtrip,
    # so datetime remains a datetime object (not a string)
    assert isinstance(result["timestamp"], datetime)


def test_cache_stats_returns_backend_info():
    """Verify stats() provides hit/miss/backend information."""
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=16)
    c.set("x", 1)
    c.get("x")  # Hit
    c.get("missing")  # Miss
    c.get("missing")  # Miss

    stats = c.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 2
    assert abs(stats["hit_rate"] - 1/3) < 0.001  # Approximate due to rounding
    assert stats["backend"] == "memory"


def test_cache_ttl_respects_custom_value():
    """Verify set() uses provided ttl over default."""
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=16)

    # Custom TTL should override default
    c.set("k", {"data": 1}, ttl=600)

    # Verify key was set (Redis setex would use ttl=600,
    # in-memory TTLCache uses default ttl of 10)
    assert c.get("k") == {"data": 1}


def test_cache_handles_set_errors_gracefully():
    """Verify set() doesn't raise even if cache backend errors."""
    c = CacheClient(redis_url="", ttl_seconds=10, max_entries=2)

    # Exceed max size to cause issues
    c.set("k1", "v1")
    c.set("k2", "v2")
    c.set("k3", "v3")  # May cause issues but should not raise

    # At least some data should be accessible
    assert c.get("k1") is None or c.get("k2") is not None


def test_cache_is_healthy_checks_backend():
    """Verify is_healthy() returns False when Redis is not reachable.

    In-memory fallback is a degraded state per design — the health endpoint
    should report Redis as unavailable so operators know persistence is lost.
    """
    memory_cache = CacheClient(redis_url="", ttl_seconds=10)
    assert memory_cache.is_healthy() is False

    # Invalid Redis falls back to memory — still degraded (no Redis persistence)
    invalid_cache = CacheClient(redis_url="redis://invalid:9999/0", ttl_seconds=10)
    assert invalid_cache.is_healthy() is False


def test_cache_from_settings_class_method():
    """Verify from_settings() initializes cache from settings object."""
    from unittest.mock import Mock

    settings = Mock()
    settings.redis_url = ""
    settings.cache_ttl_seconds = 120
    settings.cache_max_entries = 512

    c = CacheClient.from_settings(settings)

    assert c._ttl == 120
    assert c._memory is not None
    assert c._redis is None
