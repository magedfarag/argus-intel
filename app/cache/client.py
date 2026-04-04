"""Cache client with Redis primary and TTLCache fallback.

Usage::

    cache = CacheClient.from_settings(settings)
    cache.set("key", {"data": 1}, ttl=3600)
    value = cache.get("key")     # None on miss
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class CacheClient:
    """Unified cache abstraction over Redis or an in-process TTLCache."""

    def __init__(self, *, redis_url: str = "", ttl_seconds: int = 3600, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._redis: Any = None
        self._memory: Any = None
        self._hits = 0
        self._misses = 0

        if redis_url:
            try:
                import redis as redis_lib
                self._redis = redis_lib.from_url(redis_url, socket_connect_timeout=3)
                self._redis.ping()
                log.info("Cache backend: Redis (%s)", redis_url.split("@")[-1])
            except Exception as exc:  # noqa: BLE001
                log.warning("Redis unavailable (%s); using in-memory cache", exc)
                self._redis = None

        if self._redis is None:
            from cachetools import TTLCache
            self._memory = TTLCache(maxsize=max_entries, ttl=ttl_seconds)
            log.info("Cache backend: in-memory TTLCache (max=%s, ttl=%ss)", max_entries, ttl_seconds)

    @classmethod
    def from_settings(cls, settings: Any) -> "CacheClient":
        return cls(
            redis_url=settings.redis_url,
            ttl_seconds=settings.cache_ttl_seconds,
            max_entries=settings.cache_max_entries,
        )

    def get(self, key: str) -> Optional[Any]:
        try:
            if self._redis:
                raw = self._redis.get(key)
                if raw is not None:
                    self._hits += 1
                    return json.loads(raw)
            elif self._memory is not None and key in self._memory:
                self._hits += 1
                return self._memory[key]
        except Exception as exc:  # noqa: BLE001
            log.debug("Cache get error: %s", exc)
        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._ttl
        try:
            if self._redis:
                self._redis.setex(key, effective_ttl, json.dumps(value, default=str))
            elif self._memory is not None:
                self._memory[key] = value
        except Exception as exc:  # noqa: BLE001
            log.debug("Cache set error: %s", exc)

    def delete(self, key: str) -> None:
        try:
            if self._redis:
                self._redis.delete(key)
            elif self._memory is not None:
                self._memory.pop(key, None)
        except Exception as exc:  # noqa: BLE001
            log.debug("Cache delete error: %s", exc)

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits":      self._hits,
            "misses":    self._misses,
            "hit_rate":  round(self._hits / total, 4) if total else 0.0,
            "backend":   "redis" if self._redis else "memory",
        }

    def is_healthy(self) -> bool:
        """Return True only when the Redis backend is reachable.

        An in-memory fallback is a degraded state — the caller (health endpoint)
        should report Redis as unavailable so operators know persistence is lost.
        """
        try:
            if self._redis:
                self._redis.ping()
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    @property
    def backend(self) -> str:
        """Return 'redis' or 'memory' — used by health endpoint for detail."""
        return "redis" if self._redis else "memory"
