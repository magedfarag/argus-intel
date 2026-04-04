"""Unit tests for src/models/investigations.py — Phase 5 Track A."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from src.models.investigations import (
    Investigation,
    InvestigationCreateRequest,
    InvestigationListResponse,
    InvestigationNote,
    InvestigationStatus,
    InvestigationUpdateRequest,
    SavedFilter,
    WatchlistEntry,
    WatchlistEntryType,
)
from src.models.operational_layers import EvidenceLink


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc)


def _make_investigation(**kwargs) -> Investigation:
    defaults = dict(name="Test Investigation")
    defaults.update(kwargs)
    return Investigation(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Model creation with defaults
# ──────────────────────────────────────────────────────────────────────────────


def test_investigation_default_id_is_uuid():
    inv = _make_investigation()
    assert len(inv.id) == 36
    assert inv.id.count("-") == 4


def test_investigation_defaults():
    inv = _make_investigation()
    assert inv.status == InvestigationStatus.DRAFT
    assert inv.description is None
    assert inv.created_by is None
    assert inv.tags == []
    assert inv.watchlist == []
    assert inv.notes == []
    assert inv.saved_filters == []
    assert inv.evidence_links == []
    assert inv.linked_event_ids == []


def test_investigation_two_instances_have_different_ids():
    a = _make_investigation()
    b = _make_investigation()
    assert a.id != b.id


# ──────────────────────────────────────────────────────────────────────────────
# 2. Status enum values
# ──────────────────────────────────────────────────────────────────────────────


def test_status_enum_values():
    assert InvestigationStatus.DRAFT == "draft"
    assert InvestigationStatus.ACTIVE == "active"
    assert InvestigationStatus.ARCHIVED == "archived"
    assert InvestigationStatus.CLOSED == "closed"


def test_investigation_accepts_all_statuses():
    for status in InvestigationStatus:
        inv = _make_investigation(status=status)
        assert inv.status == status


# ──────────────────────────────────────────────────────────────────────────────
# 3. UTC timestamp enforcement
# ──────────────────────────────────────────────────────────────────────────────


def test_timestamps_are_utc_aware():
    inv = _make_investigation()
    assert inv.created_at.tzinfo is not None
    assert inv.updated_at.tzinfo is not None


def test_naive_created_at_rejected():
    with pytest.raises(ValidationError):
        Investigation(
            name="X",
            created_at=datetime(2026, 1, 1),  # naive
            updated_at=_NOW,
        )


def test_naive_updated_at_rejected():
    with pytest.raises(ValidationError):
        Investigation(
            name="X",
            created_at=_NOW,
            updated_at=datetime(2026, 1, 1),  # naive
        )


def test_iso_string_timestamps_accepted():
    inv = Investigation(
        name="X",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T01:00:00+00:00",
    )
    assert inv.created_at.tzinfo is not None
    assert inv.updated_at.tzinfo is not None


def test_iso_z_suffix_timestamps_accepted():
    inv = Investigation(
        name="X",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T01:00:00Z",
    )
    assert inv.created_at.tzinfo is not None


# ──────────────────────────────────────────────────────────────────────────────
# 4. updated_at >= created_at validation
# ──────────────────────────────────────────────────────────────────────────────


def test_updated_at_before_created_at_rejected():
    t_later = _NOW
    t_earlier = _NOW - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="updated_at must be >= created_at"):
        Investigation(name="X", created_at=t_later, updated_at=t_earlier)


def test_updated_at_equal_to_created_at_accepted():
    inv = Investigation(name="X", created_at=_NOW, updated_at=_NOW)
    assert inv.updated_at == inv.created_at


# ──────────────────────────────────────────────────────────────────────────────
# 5. WatchlistEntry creation
# ──────────────────────────────────────────────────────────────────────────────


def test_watchlist_entry_defaults():
    entry = WatchlistEntry(
        entry_type=WatchlistEntryType.VESSEL, identifier="123456789"
    )
    assert entry.id is not None
    assert entry.confidence == 1.0
    assert entry.label is None
    assert entry.added_at.tzinfo is not None


def test_watchlist_entry_type_values():
    assert WatchlistEntryType.VESSEL == "vessel"
    assert WatchlistEntryType.AIRCRAFT == "aircraft"
    assert WatchlistEntryType.LOCATION == "location"
    assert WatchlistEntryType.EVENT_PATTERN == "event_pattern"
    assert WatchlistEntryType.PERSON == "person"


def test_watchlist_entry_confidence_bounds():
    with pytest.raises(ValidationError):
        WatchlistEntry(entry_type=WatchlistEntryType.VESSEL, identifier="x", confidence=1.5)
    with pytest.raises(ValidationError):
        WatchlistEntry(entry_type=WatchlistEntryType.VESSEL, identifier="x", confidence=-0.1)


# ──────────────────────────────────────────────────────────────────────────────
# 6. InvestigationNote creation
# ──────────────────────────────────────────────────────────────────────────────


def test_note_creation():
    note = InvestigationNote(
        investigation_id="inv-1", content="Spotted vessel transiting chokepoint."
    )
    assert note.id is not None
    assert note.tags == []
    assert note.author is None
    assert note.created_at.tzinfo is not None


def test_note_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        InvestigationNote(
            investigation_id="inv-1",
            content="x",
            created_at=datetime(2026, 1, 1),
        )


# ──────────────────────────────────────────────────────────────────────────────
# 7. SavedFilter creation
# ──────────────────────────────────────────────────────────────────────────────


def test_saved_filter_creation():
    filt = SavedFilter(
        name="AIS gaps > 6h",
        filter_definition={"event_types": ["dark_ship_candidate"], "min_gap_hours": 6},
    )
    assert filt.id is not None
    assert filt.created_at.tzinfo is not None
    assert filt.filter_definition["min_gap_hours"] == 6


# ──────────────────────────────────────────────────────────────────────────────
# 8. InvestigationCreateRequest and UpdateRequest
# ──────────────────────────────────────────────────────────────────────────────


def test_create_request_minimal():
    req = InvestigationCreateRequest(name="Op Tempest")
    assert req.name == "Op Tempest"
    assert req.tags == []
    assert req.created_by is None


def test_update_request_all_none():
    req = InvestigationUpdateRequest()
    assert req.name is None
    assert req.status is None


# ──────────────────────────────────────────────────────────────────────────────
# 9. InvestigationListResponse
# ──────────────────────────────────────────────────────────────────────────────


def test_list_response_structure():
    inv = _make_investigation()
    resp = InvestigationListResponse(items=[inv], total=1)
    assert resp.total == 1
    assert resp.items[0].id == inv.id


# ──────────────────────────────────────────────────────────────────────────────
# 10. EvidenceLink import (from operational_layers)
# ──────────────────────────────────────────────────────────────────────────────


def test_evidence_link_attaches_to_investigation():
    link = EvidenceLink(
        evidence_id="ev-001",
        event_id="canonical-001",
        evidence_type="imagery",
    )
    inv = Investigation(name="Test", evidence_links=[link])
    assert len(inv.evidence_links) == 1
    assert inv.evidence_links[0].evidence_id == "ev-001"


# ──────────────────────────────────────────────────────────────────────────────
# 11. __all__ completeness
# ──────────────────────────────────────────────────────────────────────────────


def test_module_all_exports():
    import src.models.investigations as m
    for name in m.__all__:
        assert hasattr(m, name), f"{name} declared in __all__ but not found in module"
