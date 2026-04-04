"""Deduplication service: deterministic ID first, fuzzy fallback.

P0-6.4: Implements the two-pass deduplication strategy from
canonical-event-model.md §8:
  1. Exact match on deterministic event_id (primary key — zero overhead).
  2. Fuzzy match on (source, entity_id, event_time bucket) when the
     upstream source does not produce stable IDs.

Thread-safety: the in-memory seen-set is not threadsafe by default; inject
a Redis-backed implementation for multi-worker deployments.
"""
from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Optional, Set

from src.models.canonical_event import CanonicalEvent

logger = logging.getLogger(__name__)


class DeduplicationBackend(ABC):
    """Pluggable storage backend for the seen-id set."""

    @abstractmethod
    def has_seen(self, event_id: str) -> bool:
        """Return True if this event_id was already processed."""

    @abstractmethod
    def mark_seen(self, event_id: str) -> None:
        """Record that this event_id has been processed."""


class InMemoryDeduplicationBackend(DeduplicationBackend):
    """Non-persistent in-memory backend — suitable for tests and single-process demo."""

    def __init__(self) -> None:
        self._seen: Set[str] = set()

    def has_seen(self, event_id: str) -> bool:
        return event_id in self._seen

    def mark_seen(self, event_id: str) -> None:
        self._seen.add(event_id)

    def clear(self) -> None:
        self._seen.clear()


class DeduplicationService:
    """Determines whether an incoming CanonicalEvent is a duplicate.

    Strategy (applied in order):
    1. Exact event_id match — instant O(1) check against seen-set.
    2. Fuzzy dedupe_key match — a stable hash of (source, entity_id,
       time-bucket) used when the source emits repeated records within a
       time window (e.g., AIS position spam).

    A time bucket of 60 seconds is used for fuzzy matching to collapse
    near-simultaneous duplicates from the same entity.
    """

    FUZZY_BUCKET_SECONDS: int = 60

    def __init__(self, backend: Optional[DeduplicationBackend] = None) -> None:
        self._backend = backend or InMemoryDeduplicationBackend()

    def is_duplicate(self, event: CanonicalEvent) -> bool:
        """Return True if this event should be skipped as a duplicate."""
        # Pass 1: exact event_id
        if self._backend.has_seen(event.event_id):
            logger.debug("Duplicate (exact id): %s", event.event_id)
            return True

        # Pass 2: fuzzy dedupe_key from normalization record
        if event.normalization.dedupe_key:
            if self._backend.has_seen(event.normalization.dedupe_key):
                logger.debug("Duplicate (fuzzy key): %s", event.normalization.dedupe_key)
                return True

        return False

    def mark_processed(self, event: CanonicalEvent) -> None:
        """Record this event as processed (call after successful store)."""
        self._backend.mark_seen(event.event_id)
        if event.normalization.dedupe_key:
            self._backend.mark_seen(event.normalization.dedupe_key)

    @staticmethod
    def make_fuzzy_dedupe_key(source: str, entity_id: str, event_time: datetime) -> str:
        """Build the fuzzy dedupe key by bucketing event_time to 60-second intervals."""
        ts = event_time.astimezone(timezone.utc)
        bucket_ts = ts.replace(second=(ts.second // 60) * 60, microsecond=0)
        raw = f"{source}:{entity_id}:{bucket_ts.isoformat()}"
        return "fuzz_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
