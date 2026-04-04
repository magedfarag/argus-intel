"""In-process TTL query cache — Phase 6 Track B.

Thread-safe TTL cache for expensive read-only endpoint responses.
Cache key is caller-supplied based on stable query parameters.

TTL defaults per query window size:
  ≤ 1 day  → 60s
  ≤ 7 days → 300s
  ≤ 30 days → 600s

State is in-process per worker.  For multi-worker deployments, back this
with Redis (use app/cache/client.py which already supports Redis).

NOTE: Only apply to read-only (GET) endpoints.  Never cache mutation responses.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

# ── Default TTL ────────────────────────────────────────────────────────────────
_DEFAULT_TTL: float = 60.0


# ── Internal cache entry ───────────────────────────────────────────────────────


class _Entry:
    """Single cache slot holding a value and its expiry time."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl


# ── Cache implementation ───────────────────────────────────────────────────────


class QueryCache:
    """In-process TTL cache for read queries.

    All public methods are thread-safe via a single ``threading.Lock``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: Dict[str, _Entry] = {}
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """Return cached value or ``None`` on miss / expiry."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                self._evictions += 1
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    # ── Write ─────────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any, ttl: float = _DEFAULT_TTL) -> None:
        """Store *value* under *key* with the given TTL (seconds)."""
        with self._lock:
            self._store[key] = _Entry(value, ttl)

    def invalidate(self, key: str) -> None:
        """Remove a single key from the cache (no-op if absent)."""
        with self._lock:
            self._store.pop(key, None)

    # ── Maintenance ───────────────────────────────────────────────────────────

    def purge_expired(self) -> int:
        """Remove all expired entries.  Returns the count removed."""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, v in self._store.items() if now > v.expires_at]
            for k in expired:
                del self._store[k]
            self._evictions += len(expired)
            return len(expired)

    # ── Introspection ─────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return a point-in-time snapshot of cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            # Expire stale entries so total_entries is accurate
            now = time.monotonic()
            live_entries = sum(
                1 for v in self._store.values() if now <= v.expires_at
            )
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total else 0.0,
                "miss_rate": self._misses / total if total else 0.0,
                "evictions": self._evictions,
                "total_entries": live_entries,
            }


# ── TTL helper ────────────────────────────────────────────────────────────────


def ttl_for_window(days: float) -> float:
    """Return recommended cache TTL (seconds) for a given query window.

    Args:
        days: query time-window width in days (fractional OK).

    Returns:
        60  for ≤ 1-day windows
        300 for ≤ 7-day windows
        600 for longer windows
    """
    if days <= 1:
        return 60.0
    if days <= 7:
        return 300.0
    return 600.0


# ── Module-level singleton ────────────────────────────────────────────────────
# Double-checked locking for lazy initialisation.

_singleton_lock = threading.Lock()
_default_cache: Optional[QueryCache] = None


def get_query_cache() -> QueryCache:
    """Return (and lazily create) the process-wide QueryCache singleton."""
    global _default_cache
    if _default_cache is None:
        with _singleton_lock:
            if _default_cache is None:
                _default_cache = QueryCache()
    return _default_cache


def reset_query_cache() -> None:
    """Replace the singleton with a fresh instance (for testing only)."""
    global _default_cache
    with _singleton_lock:
        _default_cache = QueryCache()
