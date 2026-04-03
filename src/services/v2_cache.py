"""Typed cache helpers for V2 API services.

P5-1.1: Hot timeline windows — 5-minute TTL
P5-1.2: STAC search results — 15-minute TTL, keyed by aoi+time+collections
P5-1.3: Playback query results — 2-minute TTL, keyed by query hash
P5-1.4: Source health snapshots — 60-second TTL
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from app.cache.client import CacheClient

log = logging.getLogger(__name__)

# ── TTL constants ──────────────────────────────────────────────────────────────
_TTL_TIMELINE: int = 300       # 5 minutes for hot timeline windows
_TTL_STAC_SEARCH: int = 900    # 15 minutes for STAC search results
_TTL_PLAYBACK: int = 120       # 2 minutes for playback segments
_TTL_SOURCE_HEALTH: int = 60   # 60 seconds for source health snapshots

_KEY_PREFIX_TIMELINE: str = "v2:timeline:"
_KEY_PREFIX_STAC: str = "v2:stac:"
_KEY_PREFIX_PLAYBACK: str = "v2:playback:"
_KEY_PREFIX_HEALTH: str = "v2:health:"


def _hash_dict(d: Dict[str, Any]) -> str:
    """Return a stable 16-char hex hash from a dict (values must be JSON-serialisable)."""
    canonical = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class V2CacheService:
    """Typed cache layer for all V2 services.

    Wraps the underlying CacheClient with typed methods whose keys encode
    query semantics.  All methods degrade silently on cache errors.
    """

    def __init__(self, cache: CacheClient) -> None:
        self._cache = cache

    # ── P5-1.1: Timeline windows ───────────────────────────────────────────────

    def get_timeline(
        self,
        aoi_id: Optional[str],
        start: str,
        end: str,
        bucket_minutes: int,
    ) -> Optional[Dict[str, Any]]:
        key = f"{_KEY_PREFIX_TIMELINE}{_hash_dict({'a': aoi_id, 's': start, 'e': end, 'b': bucket_minutes})}"
        return self._cache.get(key)

    def set_timeline(
        self,
        aoi_id: Optional[str],
        start: str,
        end: str,
        bucket_minutes: int,
        value: Dict[str, Any],
    ) -> None:
        key = f"{_KEY_PREFIX_TIMELINE}{_hash_dict({'a': aoi_id, 's': start, 'e': end, 'b': bucket_minutes})}"
        self._cache.set(key, value, ttl=_TTL_TIMELINE)

    # ── P5-1.2: STAC search results ────────────────────────────────────────────

    def get_stac_search(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        key = f"{_KEY_PREFIX_STAC}{_hash_dict(params)}"
        return self._cache.get(key)

    def set_stac_search(self, params: Dict[str, Any], value: Dict[str, Any]) -> None:
        key = f"{_KEY_PREFIX_STAC}{_hash_dict(params)}"
        self._cache.set(key, value, ttl=_TTL_STAC_SEARCH)

    # ── P5-1.3: Playback query results ─────────────────────────────────────────

    def get_playback(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        key = f"{_KEY_PREFIX_PLAYBACK}{_hash_dict(params)}"
        return self._cache.get(key)

    def set_playback(self, params: Dict[str, Any], value: Dict[str, Any]) -> None:
        key = f"{_KEY_PREFIX_PLAYBACK}{_hash_dict(params)}"
        self._cache.set(key, value, ttl=_TTL_PLAYBACK)

    # ── P5-1.4: Source health snapshots ───────────────────────────────────────

    def get_source_health(self, connector_id: str) -> Optional[Dict[str, Any]]:
        key = f"{_KEY_PREFIX_HEALTH}{connector_id}"
        return self._cache.get(key)

    def set_source_health(self, connector_id: str, value: Dict[str, Any]) -> None:
        key = f"{_KEY_PREFIX_HEALTH}{connector_id}"
        self._cache.set(key, value, ttl=_TTL_SOURCE_HEALTH)

    def get_all_source_health(self) -> Optional[Dict[str, Any]]:
        key = f"{_KEY_PREFIX_HEALTH}__all__"
        return self._cache.get(key)

    def set_all_source_health(self, value: Dict[str, Any]) -> None:
        key = f"{_KEY_PREFIX_HEALTH}__all__"
        self._cache.set(key, value, ttl=_TTL_SOURCE_HEALTH)

    def invalidate_source_health(self, connector_id: Optional[str] = None) -> None:
        """Delete cached health snapshot(s). Redis-backed only; no-op for TTLCache."""
        try:
            if connector_id:
                self._cache.delete(f"{_KEY_PREFIX_HEALTH}{connector_id}")
            self._cache.delete(f"{_KEY_PREFIX_HEALTH}__all__")
        except Exception as exc:  # noqa: BLE001
            log.debug("Cache invalidation skipped: %s", exc)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        """Return hit/miss counters from the underlying cache client."""
        return {"hits": self._cache._hits, "misses": self._cache._misses}
