"""Unit tests for Redis-backed circuit breaker (P3-4).

Tests verify that:
- Redis backend initializes when URL is provided
- Falls back to in-memory when Redis is unavailable
- State sync round-trips through Redis
- Graceful degradation on Redis errors
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.resilience.circuit_breaker import CBState, CircuitBreaker


class TestRedisBackend:
    """Test Redis vs memory backend selection."""

    def test_memory_backend_when_no_url(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        assert cb.backend == "memory"
        assert cb._redis is None

    def test_memory_backend_when_empty_url(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1, redis_url="")
        assert cb.backend == "memory"

    def test_memory_fallback_on_bad_url(self):
        cb = CircuitBreaker(
            failure_threshold=3, recovery_timeout=1,
            redis_url="redis://nonexistent-host:9999/0",
        )
        assert cb.backend == "memory"

    @patch("redis.from_url")
    def test_redis_backend_when_url_valid(self, mock_from_url):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client
        cb = CircuitBreaker(
            failure_threshold=3, recovery_timeout=1,
            redis_url="redis://localhost:6379/0",
        )
        assert cb.backend == "redis"
        assert cb._redis is mock_client


class TestRedisSyncBehaviour:
    """Test state synchronization to/from Redis."""

    @pytest.fixture()
    def cb_with_mock_redis(self):
        """CircuitBreaker with a mocked Redis client."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        cb._redis = mock_redis
        return cb, mock_redis

    def test_save_to_redis_on_record_success(self, cb_with_mock_redis):
        cb, mock_redis = cb_with_mock_redis
        cb.record_success("sentinel2")
        assert mock_redis.setex.called
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        assert "circuit_breaker:sentinel2" in key
        data = json.loads(call_args[0][2])
        assert data["state"] == "closed"
        assert data["failure_count"] == 0

    def test_save_to_redis_on_record_failure(self, cb_with_mock_redis):
        cb, mock_redis = cb_with_mock_redis
        cb.record_failure("sentinel2")
        assert mock_redis.setex.called
        data = json.loads(mock_redis.setex.call_args[0][2])
        assert data["failure_count"] == 1

    def test_save_open_state_after_threshold(self, cb_with_mock_redis):
        cb, mock_redis = cb_with_mock_redis
        for _ in range(3):
            cb.record_failure("s2")
        last_data = json.loads(mock_redis.setex.call_args[0][2])
        assert last_data["state"] == "open"
        assert last_data["failure_count"] == 3

    def test_sync_from_redis_on_is_open(self, cb_with_mock_redis):
        cb, mock_redis = cb_with_mock_redis
        # Track what gets saved to Redis so subsequent reads see updated state
        saved_data = {}

        def mock_get(key):
            if key in saved_data:
                return saved_data[key]
            return json.dumps({
                "state": "open",
                "failure_count": 5,
                "last_failure_ts": 0.0,  # very old → will transition to half_open
            })

        def mock_setex(key, ttl, value):
            saved_data[key] = value

        mock_redis.get.side_effect = mock_get
        mock_redis.setex.side_effect = mock_setex

        # With last_failure_ts=0 and recovery_timeout=60, monotonic() is > 60
        result = cb.is_open("sentinel2")
        # Should have transitioned to HALF_OPEN (probe allowed)
        assert result is False
        assert cb.status("sentinel2") == CBState.HALF_OPEN

    def test_sync_from_redis_on_status(self, cb_with_mock_redis):
        cb, mock_redis = cb_with_mock_redis
        mock_redis.get.return_value = json.dumps({
            "state": "closed",
            "failure_count": 0,
            "last_failure_ts": 0.0,
        })
        assert cb.status("landsat") == CBState.CLOSED

    def test_status_all_syncs_all_providers(self, cb_with_mock_redis):
        cb, mock_redis = cb_with_mock_redis
        cb.record_success("sentinel2")
        cb.record_success("landsat")
        result = cb.status_all()
        assert "sentinel2" in result
        assert "landsat" in result


class TestRedisGracefulDegradation:
    """Test that Redis errors don't break circuit breaker."""

    @pytest.fixture()
    def cb_with_failing_redis(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("Redis down")
        mock_redis.setex.side_effect = ConnectionError("Redis down")
        cb._redis = mock_redis
        return cb

    def test_record_failure_survives_redis_error(self, cb_with_failing_redis):
        cb = cb_with_failing_redis
        # Should not raise
        cb.record_failure("sentinel2")
        assert cb._get("sentinel2").failure_count == 1

    def test_record_success_survives_redis_error(self, cb_with_failing_redis):
        cb = cb_with_failing_redis
        cb.record_success("sentinel2")
        assert cb._get("sentinel2").state == CBState.CLOSED

    def test_is_open_survives_redis_error(self, cb_with_failing_redis):
        cb = cb_with_failing_redis
        # Should not raise, falls back to local state
        result = cb.is_open("sentinel2")
        assert result is False

    def test_status_survives_redis_error(self, cb_with_failing_redis):
        cb = cb_with_failing_redis
        assert cb.status("sentinel2") == CBState.CLOSED


class TestOriginalBehaviourPreserved:
    """Ensure in-memory circuit breaker still works identically."""

    def test_closed_to_open_transition(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            cb.record_failure("test_provider")
        assert cb.status("test_provider") == CBState.OPEN

    def test_is_open_blocks_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=9999)
        cb.record_failure("p")
        cb.record_failure("p")
        assert cb.is_open("p") is True

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        cb.record_failure("p")
        cb.record_failure("p")
        assert cb.status("p") == CBState.OPEN
        # Simulate HALF_OPEN → success
        cb._get("p").state = CBState.HALF_OPEN
        cb.record_success("p")
        assert cb.status("p") == CBState.CLOSED

    def test_per_provider_isolation(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        cb.record_failure("a")
        cb.record_failure("a")
        assert cb.is_open("a") is True
        assert cb.is_open("b") is False