"""In-process circuit breaker for external provider calls.

States: CLOSED (normal) → OPEN (after N failures) → HALF-OPEN (probe) → CLOSED

Thread-safe via threading.Lock.  Optionally backed by Redis for shared state
across multiple workers (P3-4).  Falls back to in-process state when Redis
is unavailable.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "circuit_breaker:"
_REDIS_TTL = 3600  # 1 hour TTL for Redis keys


class CBState(str, Enum):
    CLOSED    = "closed"    # normal operation
    OPEN      = "open"      # blocking calls after too many failures
    HALF_OPEN = "half_open" # allowing one probe request


@dataclass
class _ProviderState:
    state:          CBState = CBState.CLOSED
    failure_count:  int     = 0
    last_failure_ts: float  = 0.0
    lock: threading.Lock    = field(default_factory=threading.Lock, repr=False)


class CircuitBreaker:
    """Circuit breaker registry, one entry per provider name.

    When redis_url is provided, state is stored in Redis for cross-worker
    sharing.  Falls back to in-process state on Redis errors.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        redis_url: str = "",
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout  = recovery_timeout
        self._states: Dict[str, _ProviderState] = {}
        self._redis: Any = None

        if redis_url:
            try:
                import redis as redis_lib
                self._redis = redis_lib.from_url(redis_url, socket_connect_timeout=3)
                self._redis.ping()
                log.info("CircuitBreaker backend: Redis")
            except Exception as exc:  # noqa: BLE001
                log.warning("CircuitBreaker Redis unavailable (%s); using in-process state", exc)
                self._redis = None

    @property
    def backend(self) -> str:
        """Return storage backend type."""
        return "redis" if self._redis else "memory"

    def _get(self, provider: str) -> _ProviderState:
        if provider not in self._states:
            self._states[provider] = _ProviderState()
        return self._states[provider]

    def _redis_key(self, provider: str) -> str:
        return f"{_REDIS_KEY_PREFIX}{provider}"

    def _load_from_redis(self, provider: str) -> Optional[Dict[str, Any]]:
        """Load state from Redis; return None on miss or error."""
        if not self._redis:
            return None
        try:
            raw = self._redis.get(self._redis_key(provider))
            if raw:
                return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            log.debug("Redis CB load error for %s: %s", provider, exc)
        return None

    def _save_to_redis(self, provider: str, ps: _ProviderState) -> None:
        """Persist state to Redis; silently fails on error."""
        if not self._redis:
            return
        try:
            data = {
                "state": ps.state.value,
                "failure_count": ps.failure_count,
                "last_failure_ts": ps.last_failure_ts,
            }
            self._redis.setex(
                self._redis_key(provider),
                _REDIS_TTL,
                json.dumps(data),
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("Redis CB save error for %s: %s", provider, exc)

    def _sync_from_redis(self, provider: str, ps: _ProviderState) -> None:
        """Merge Redis state into local in-process state."""
        data = self._load_from_redis(provider)
        if data:
            ps.state = CBState(data.get("state", "closed"))
            ps.failure_count = data.get("failure_count", 0)
            ps.last_failure_ts = data.get("last_failure_ts", 0.0)

    def is_open(self, provider: str) -> bool:
        """Return True if calls to *provider* should be blocked."""
        ps = self._get(provider)
        with ps.lock:
            self._sync_from_redis(provider, ps)
            if ps.state == CBState.OPEN:
                if time.monotonic() - ps.last_failure_ts >= self._recovery_timeout:
                    ps.state = CBState.HALF_OPEN
                    self._save_to_redis(provider, ps)
                    log.info("Circuit breaker HALF-OPEN for %s", provider)
                    return False   # allow probe
                return True
            return False

    def record_success(self, provider: str) -> None:
        ps = self._get(provider)
        with ps.lock:
            if ps.state != CBState.CLOSED:
                log.info("Circuit breaker CLOSED for %s after success", provider)
            ps.state         = CBState.CLOSED
            ps.failure_count = 0
            self._save_to_redis(provider, ps)

    def record_failure(self, provider: str) -> None:
        ps = self._get(provider)
        with ps.lock:
            self._sync_from_redis(provider, ps)
            ps.failure_count  += 1
            ps.last_failure_ts = time.monotonic()
            if ps.state == CBState.HALF_OPEN or ps.failure_count >= self._failure_threshold:
                ps.state = CBState.OPEN
                log.warning(
                    "Circuit breaker OPEN for %s (%d failures)", provider, ps.failure_count
                )
            self._save_to_redis(provider, ps)

    def status(self, provider: str) -> CBState:
        ps = self._get(provider)
        self._sync_from_redis(provider, ps)
        return ps.state

    def status_all(self) -> Dict[str, str]:
        """Return state of all tracked providers."""
        result: Dict[str, str] = {}
        for name, ps in self._states.items():
            self._sync_from_redis(name, ps)
            result[name] = ps.state.value
        return result
