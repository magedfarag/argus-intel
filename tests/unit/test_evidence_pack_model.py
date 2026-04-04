"""Unit tests for EvidencePack models and EvidencePackService rendering — Phase 5 Track B."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.models.evidence_pack import (
    EvidencePack,
    EvidencePackFormat,
    EvidencePackRequest,
    EvidencePackSection,
    LayerSummaryEntry,
    ProvenanceRecord,
    TimelineEntry,
)
from src.services.evidence_pack_service import EvidencePackService


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def service() -> EvidencePackService:
    svc = EvidencePackService()
    return svc


@pytest.fixture()
def minimal_pack() -> EvidencePack:
    return EvidencePack(title="Test Pack")


@pytest.fixture()
def full_pack() -> EvidencePack:
    return EvidencePack(
        title="Full Pack",
        description="Comprehensive test pack",
        investigation_id="inv-001",
        created_by="analyst",
        time_window_start=_NOW,
        time_window_end=_NOW,
        sections_included=[EvidencePackSection.TIMELINE, EvidencePackSection.PROVENANCE],
        timeline=[
            TimelineEntry(
                timestamp=_NOW,
                event_type="ship_position",
                event_id="evt-001",
                summary="Vessel detected",
                source="ais-stream",
                confidence=0.9,
                layer="ship_position",
            )
        ],
        layer_summaries=[
            LayerSummaryEntry(
                layer_name="ship_position",
                event_count=1,
                time_range_start=_NOW,
                time_range_end=_NOW,
                coverage_description="1 event across 1 source",
                sources=["ais-stream"],
            )
        ],
        provenance_records=[
            ProvenanceRecord(
                source_name="ais-stream",
                source_type="telemetry",
                event_count=1,
                license="check-provider-terms",
            )
        ],
        event_ids=["evt-001"],
        notes=["Manual note from analyst"],
        total_events=1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. EvidencePack creation with defaults
# ──────────────────────────────────────────────────────────────────────────────

def test_evidence_pack_defaults():
    pack = EvidencePack(title="Defaults")
    assert pack.pack_id  # auto UUID
    assert pack.title == "Defaults"
    assert pack.timeline == []
    assert pack.layer_summaries == []
    assert pack.provenance_records == []
    assert pack.event_ids == []
    assert pack.total_events == 0
    assert pack.export_format == EvidencePackFormat.JSON
    assert pack.created_at.tzinfo is not None


# ──────────────────────────────────────────────────────────────────────────────
# 2. EvidencePackFormat enum values
# ──────────────────────────────────────────────────────────────────────────────

def test_evidence_pack_format_values():
    assert EvidencePackFormat.JSON == "json"
    assert EvidencePackFormat.MARKDOWN == "markdown"
    assert EvidencePackFormat.GEOJSON == "geojson"
    assert len(EvidencePackFormat) == 3


# ──────────────────────────────────────────────────────────────────────────────
# 3. EvidencePackSection enum values
# ──────────────────────────────────────────────────────────────────────────────

def test_evidence_pack_section_values():
    expected = {
        "timeline", "layer_summary", "provenance", "images",
        "entities", "notes", "evidence_links", "absence_signals",
    }
    actual = {s.value for s in EvidencePackSection}
    assert actual == expected


# ──────────────────────────────────────────────────────────────────────────────
# 4. TimelineEntry UTC datetime
# ──────────────────────────────────────────────────────────────────────────────

def test_timeline_entry_utc():
    entry = TimelineEntry(
        timestamp=_NOW,
        event_type="aircraft_position",
        event_id="e-1",
        summary="Aircraft overhead",
        source="opensky",
        layer="aircraft_position",
    )
    assert entry.timestamp.tzinfo is not None
    assert entry.confidence is None


def test_timeline_entry_rejects_naive_datetime():
    with pytest.raises(ValueError):
        TimelineEntry(
            timestamp=datetime(2026, 4, 4, 12, 0, 0),  # naive
            event_type="x",
            event_id="x",
            summary="x",
            source="x",
            layer="x",
        )


# ──────────────────────────────────────────────────────────────────────────────
# 5. LayerSummaryEntry construction
# ──────────────────────────────────────────────────────────────────────────────

def test_layer_summary_entry_construction():
    ls = LayerSummaryEntry(
        layer_name="gps_jamming_event",
        event_count=5,
        time_range_start=_NOW,
        time_range_end=_NOW,
        coverage_description="5 events across 2 sources",
        sources=["adsbexchange", "flightradar24"],
    )
    assert ls.layer_name == "gps_jamming_event"
    assert ls.event_count == 5
    assert ls.sources == ["adsbexchange", "flightradar24"]


# ──────────────────────────────────────────────────────────────────────────────
# 6. ProvenanceRecord construction
# ──────────────────────────────────────────────────────────────────────────────

def test_provenance_record_construction():
    pr = ProvenanceRecord(
        source_name="copernicus-cdse",
        source_type="imagery_catalog",
        event_count=12,
        license="check-provider-terms",
    )
    assert pr.source_name == "copernicus-cdse"
    assert pr.event_count == 12
    assert pr.retrieval_timestamp is None


# ──────────────────────────────────────────────────────────────────────────────
# 7. EvidencePackRequest defaults — all sections included
# ──────────────────────────────────────────────────────────────────────────────

def test_evidence_pack_request_defaults_all_sections():
    req = EvidencePackRequest(title="My Pack")
    all_sections = set(EvidencePackSection)
    assert set(req.sections) == all_sections
    assert req.export_format == EvidencePackFormat.JSON
    assert req.include_timeline is True
    assert req.include_layer_summaries is True
    assert req.include_provenance is True
    assert req.event_ids is None


# ──────────────────────────────────────────────────────────────────────────────
# 8. render_pack JSON produces valid JSON bytes
# ──────────────────────────────────────────────────────────────────────────────

def test_render_json_valid(service, full_pack):
    raw = service.render_pack(full_pack, EvidencePackFormat.JSON)
    assert isinstance(raw, bytes)
    parsed = json.loads(raw)
    assert parsed["title"] == "Full Pack"
    assert parsed["total_events"] == 1
    assert "timeline" in parsed
    assert len(parsed["timeline"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# 9. render_pack MARKDOWN contains title and timeline header
# ──────────────────────────────────────────────────────────────────────────────

def test_render_markdown_contains_title_and_timeline(service, full_pack):
    raw = service.render_pack(full_pack, EvidencePackFormat.MARKDOWN)
    assert isinstance(raw, bytes)
    text = raw.decode("utf-8")
    assert "# Evidence Pack: Full Pack" in text
    assert "## Timeline" in text
    assert "## Layer Summary" in text
    assert "## Provenance" in text
    assert "## Notes" in text


# ──────────────────────────────────────────────────────────────────────────────
# 10. render_pack GEOJSON is a valid FeatureCollection
# ──────────────────────────────────────────────────────────────────────────────

def test_render_geojson_valid_feature_collection(service, minimal_pack):
    raw = service.render_pack(minimal_pack, EvidencePackFormat.GEOJSON)
    assert isinstance(raw, bytes)
    parsed = json.loads(raw)
    assert parsed["type"] == "FeatureCollection"
    assert "features" in parsed
    assert isinstance(parsed["features"], list)


# ──────────────────────────────────────────────────────────────────────────────
# 11. EvidencePack rejects naive created_at
# ──────────────────────────────────────────────────────────────────────────────

def test_evidence_pack_rejects_naive_created_at():
    with pytest.raises(ValueError):
        EvidencePack(title="Bad", created_at=datetime(2026, 4, 4, 0, 0, 0))


# ──────────────────────────────────────────────────────────────────────────────
# 12. EvidencePack pack_id is unique per instance
# ──────────────────────────────────────────────────────────────────────────────

def test_evidence_pack_unique_ids():
    p1 = EvidencePack(title="A")
    p2 = EvidencePack(title="B")
    assert p1.pack_id != p2.pack_id


# ──────────────────────────────────────────────────────────────────────────────
# 13. render_pack MARKDOWN includes investigation_id
# ──────────────────────────────────────────────────────────────────────────────

def test_render_markdown_investigation_id(service, full_pack):
    text = service.render_pack(full_pack, EvidencePackFormat.MARKDOWN).decode("utf-8")
    assert "inv-001" in text


# ──────────────────────────────────────────────────────────────────────────────
# 14. render_pack MARKDOWN standalone label when no investigation
# ──────────────────────────────────────────────────────────────────────────────

def test_render_markdown_standalone(service, minimal_pack):
    text = service.render_pack(minimal_pack, EvidencePackFormat.MARKDOWN).decode("utf-8")
    assert "standalone" in text
