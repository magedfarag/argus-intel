"""In-memory investigation store — Phase 5 Track A.

Follows the same pattern as src/services/event_store.py:
  - module-level singleton dict + threading.Lock
  - class-based store with thin CRUD methods
  - get_default_investigation_store() returns the process-wide singleton

All mutations copy the existing Investigation and replace it so callers
always receive fully validated Pydantic models.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.models.investigations import (
    EvidenceLink,
    Investigation,
    InvestigationCreateRequest,
    InvestigationNote,
    InvestigationStatus,
    InvestigationUpdateRequest,
    SavedFilter,
    WatchlistEntry,
)


class InvestigationStore:
    """Thread-safe in-memory CRUD store for Investigation entities."""

    def __init__(self) -> None:
        self._store: Dict[str, Investigation] = {}
        self._lock = threading.Lock()

    # ── Write ops ─────────────────────────────────────────────────────────────

    def create(self, req: InvestigationCreateRequest) -> Investigation:
        """Persist a new investigation derived from *req*."""
        inv = Investigation(
            name=req.name,
            description=req.description,
            created_by=req.created_by,
            tags=list(req.tags),
        )
        with self._lock:
            self._store[inv.id] = inv
        return inv

    def update(
        self, investigation_id: str, req: InvestigationUpdateRequest
    ) -> Optional[Investigation]:
        """Apply non-None fields from *req* and refresh updated_at."""
        with self._lock:
            existing = self._store.get(investigation_id)
            if existing is None:
                return None
            data = existing.model_dump()
            if req.name is not None:
                data["name"] = req.name
            if req.description is not None:
                data["description"] = req.description
            if req.status is not None:
                data["status"] = req.status
            if req.tags is not None:
                data["tags"] = list(req.tags)
            data["updated_at"] = datetime.now(timezone.utc)
            updated = Investigation.model_validate(data)
            self._store[investigation_id] = updated
        return updated

    def delete(self, investigation_id: str) -> bool:
        """Remove an investigation.  Returns True if it existed."""
        with self._lock:
            return self._store.pop(investigation_id, None) is not None

    def add_note(
        self, investigation_id: str, note: InvestigationNote
    ) -> Optional[Investigation]:
        """Append *note* to the investigation's notes list."""
        with self._lock:
            existing = self._store.get(investigation_id)
            if existing is None:
                return None
            data = existing.model_dump()
            data["notes"] = data.get("notes", []) + [note.model_dump()]
            data["updated_at"] = datetime.now(timezone.utc)
            updated = Investigation.model_validate(data)
            self._store[investigation_id] = updated
        return updated

    def add_watchlist_entry(
        self, investigation_id: str, entry: WatchlistEntry
    ) -> Optional[Investigation]:
        """Append *entry* to the investigation's watchlist."""
        with self._lock:
            existing = self._store.get(investigation_id)
            if existing is None:
                return None
            data = existing.model_dump()
            data["watchlist"] = data.get("watchlist", []) + [entry.model_dump()]
            data["updated_at"] = datetime.now(timezone.utc)
            updated = Investigation.model_validate(data)
            self._store[investigation_id] = updated
        return updated

    def add_evidence_link(
        self, investigation_id: str, link: EvidenceLink
    ) -> Optional[Investigation]:
        """Idempotently attach an evidence link (keyed by evidence_id)."""
        with self._lock:
            existing = self._store.get(investigation_id)
            if existing is None:
                return None
            data = existing.model_dump()
            links = data.get("evidence_links", [])
            # Idempotency: skip if evidence_id already present
            existing_ids = {el["evidence_id"] for el in links}
            if link.evidence_id not in existing_ids:
                links.append(link.model_dump())
                data["evidence_links"] = links
                data["updated_at"] = datetime.now(timezone.utc)
                updated = Investigation.model_validate(data)
                self._store[investigation_id] = updated
            else:
                updated = existing
        return updated

    def add_saved_filter(
        self, investigation_id: str, filt: SavedFilter
    ) -> Optional[Investigation]:
        """Append a saved filter to the investigation."""
        with self._lock:
            existing = self._store.get(investigation_id)
            if existing is None:
                return None
            data = existing.model_dump()
            data["saved_filters"] = data.get("saved_filters", []) + [filt.model_dump()]
            data["updated_at"] = datetime.now(timezone.utc)
            updated = Investigation.model_validate(data)
            self._store[investigation_id] = updated
        return updated

    # ── Read ops ──────────────────────────────────────────────────────────────

    def get(self, investigation_id: str) -> Optional[Investigation]:
        with self._lock:
            return self._store.get(investigation_id)

    def list_all(
        self, status: Optional[InvestigationStatus] = None
    ) -> List[Investigation]:
        with self._lock:
            items = list(self._store.values())
        if status is not None:
            items = [i for i in items if i.status == status]
        # Newest first
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items

    def clear(self) -> None:
        """Remove all investigations — used in tests."""
        with self._lock:
            self._store.clear()


# ── Process-wide singleton ────────────────────────────────────────────────────

_default_store: Optional[InvestigationStore] = None
_singleton_lock = threading.Lock()


def get_default_investigation_store() -> InvestigationStore:
    """Return the process-wide InvestigationStore singleton."""
    global _default_store
    if _default_store is None:
        with _singleton_lock:
            if _default_store is None:
                _default_store = InvestigationStore()
    return _default_store
