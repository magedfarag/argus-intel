"""In-memory AOI store — thin backing layer for the CRUD API.

Replaced by a PostGIS-backed implementation in P0-4 once the database
migration is complete.  The store interface is kept intentionally thin so
swapping backends requires only a new class, no router changes.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from uuid import uuid4

from src.models.aoi import AOICreate, AOIResponse, AOIUpdate


class AOIStore:
    """Thread-safe in-memory AOI repository."""

    def __init__(self) -> None:
        self._store: dict[str, AOIResponse] = {}
        self._lock = threading.Lock()

    def create(self, payload: AOICreate) -> AOIResponse:
        now = datetime.now(UTC)
        aoi = AOIResponse(
            id=str(uuid4()),
            **payload.model_dump(),
            created_at=now,
            updated_at=now,
            deleted=False,
        )
        with self._lock:
            self._store[aoi.id] = aoi
        return aoi

    def get(self, aoi_id: str) -> AOIResponse | None:
        with self._lock:
            aoi = self._store.get(aoi_id)
        if aoi and not aoi.deleted:
            return aoi
        return None

    def list_active(self, page: int = 1, page_size: int = 20) -> list[AOIResponse]:
        with self._lock:
            active = [a for a in self._store.values() if not a.deleted]
        active.sort(key=lambda a: a.created_at, reverse=True)
        start = (page - 1) * page_size
        return active[start : start + page_size]

    def count_active(self) -> int:
        with self._lock:
            return sum(1 for a in self._store.values() if not a.deleted)

    def clear(self) -> None:
        """Remove all AOIs from the in-memory store.

        Used by demo startup reseeding to prevent stale AOI IDs from surviving
        across lifespan restarts in the same interpreter.
        """
        with self._lock:
            self._store.clear()

    def update(self, aoi_id: str, patch: AOIUpdate) -> AOIResponse | None:
        with self._lock:
            existing = self._store.get(aoi_id)
            if not existing or existing.deleted:
                return None
            updates = patch.model_dump(exclude_none=True)
            data = existing.model_dump()
            data.update(updates)
            data["updated_at"] = datetime.now(UTC)
            updated = AOIResponse(**data)
            self._store[aoi_id] = updated
        return updated

    def soft_delete(self, aoi_id: str) -> bool:
        with self._lock:
            existing = self._store.get(aoi_id)
            if not existing or existing.deleted:
                return False
            data = existing.model_dump()
            data["deleted"] = True
            data["updated_at"] = datetime.now(UTC)
            self._store[aoi_id] = AOIResponse(**data)
        return True
