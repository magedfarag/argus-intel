"""Unit tests for BaseConnector, ConnectorRegistry, NormalizationPipeline and DeduplicationService.

P0-6.5: ≥15 tests.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from src.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorHealthStatus,
    ConnectorUnavailableError,
    NormalizationError,
)
from src.connectors.registry import ConnectorRegistry
from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.normalization.deduplication import (
    DeduplicationService,
    InMemoryDeduplicationBackend,
)
from src.normalization.pipeline import NormalizationPipeline, PipelineResult


# ── Fixture connectors ────────────────────────────────────────────────────────

def _make_event(source: str = "test-src", entity_id: str = "e001") -> CanonicalEvent:
    return CanonicalEvent(
        event_id=make_event_id(source, entity_id, "2026-04-01T10:00:00Z"),
        source=source,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        event_type=EventType.IMAGERY_ACQUISITION,
        event_time=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 4, 1, 10, 1, 0, tzinfo=timezone.utc),
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        centroid={"type": "Point", "coordinates": [0.5, 0.5]},
        attributes={},
        normalization=NormalizationRecord(normalized_by="test-connector"),
        provenance=ProvenanceRecord(raw_source_ref="s3://bucket/test.json"),
        license=LicenseRecord(),
    )


class GoodConnector(BaseConnector):
    connector_id = "good"
    display_name = "Good Connector"
    source_type = "imagery_catalog"

    def connect(self) -> None:
        pass  # always succeeds

    def fetch(self, geometry, start_time, end_time, **kwargs) -> List[Dict[str, Any]]:
        return [{"id": "scene-001"}]

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        return _make_event(entity_id=raw["id"])

    def health(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(connector_id="good", healthy=True, message="ok")


class FailingConnector(BaseConnector):
    connector_id = "failing"
    display_name = "Always Failing"
    source_type = "imagery_catalog"

    def connect(self) -> None:
        raise ConnectorUnavailableError("test: remote unreachable")

    def fetch(self, geometry, start_time, end_time, **kwargs) -> List[Dict[str, Any]]:
        raise ConnectorUnavailableError("test: remote unreachable")

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        raise NormalizationError("bad record")

    def health(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(connector_id="failing", healthy=False, message="unreachable")


class NormalizationErrorConnector(GoodConnector):
    connector_id = "bad-normalizer"

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        raise NormalizationError("cannot parse: missing required field")


# ── BaseConnector tests ───────────────────────────────────────────────────────

class TestBaseConnector:
    def test_fetch_and_normalize_returns_events_and_empty_warnings_on_success(self):
        c = GoodConnector()
        events, warnings = c.fetch_and_normalize(
            geometry={"type": "Polygon", "coordinates": []},
            start_time=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )
        assert len(events) == 1
        assert warnings == []

    def test_fetch_and_normalize_collects_normalization_errors_as_warnings(self):
        c = NormalizationErrorConnector()
        events, warnings = c.fetch_and_normalize(
            geometry={"type": "Polygon", "coordinates": []},
            start_time=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )
        assert events == []
        assert len(warnings) == 1
        assert "normalization skipped" in warnings[0]

    def test_quota_status_default_returns_available(self):
        c = GoodConnector()
        status = c.quota_status()
        assert status["available"] is True


# ── ConnectorRegistry tests ───────────────────────────────────────────────────

class TestConnectorRegistry:
    def test_register_good_connector_makes_it_available(self):
        registry = ConnectorRegistry()
        registry.register(GoodConnector())
        assert registry.is_available("good")

    def test_register_failing_connector_registers_but_disabled(self):
        registry = ConnectorRegistry()
        registry.register(FailingConnector())
        assert "failing" in {c.connector_id for c in registry.all_connectors(include_disabled=True)}
        assert not registry.is_available("failing")

    def test_get_returns_none_for_disabled_connector(self):
        registry = ConnectorRegistry()
        registry.register(FailingConnector())
        assert registry.get("failing") is None

    def test_all_connectors_excludes_disabled_by_default(self):
        registry = ConnectorRegistry()
        registry.register(GoodConnector())
        registry.register(FailingConnector())
        active = registry.all_connectors()
        assert all(c.connector_id != "failing" for c in active)

    def test_disable_and_enable_toggle(self):
        registry = ConnectorRegistry()
        registry.register(GoodConnector())
        assert registry.is_available("good")
        registry.disable("good")
        assert not registry.is_available("good")
        registry.enable("good")
        assert registry.is_available("good")

    def test_connectors_by_source_type_filters_correctly(self):
        registry = ConnectorRegistry()
        registry.register(GoodConnector())
        imagery = registry.connectors_by_source_type("imagery_catalog")
        assert len(imagery) == 1
        telemetry = registry.connectors_by_source_type("telemetry")
        assert telemetry == []

    def test_health_snapshot_returns_entry_per_connector(self):
        registry = ConnectorRegistry()
        registry.register(GoodConnector())
        snapshot = registry.health_snapshot()
        assert "good" in snapshot
        assert snapshot["good"].healthy is True


# ── NormalizationPipeline tests ───────────────────────────────────────────────

class TestNormalizationPipeline:
    def test_pipeline_processes_all_valid_records(self):
        connector = GoodConnector()
        pipeline = NormalizationPipeline(connector)
        result = pipeline.run([{"id": "scene-001"}, {"id": "scene-002"}])
        assert len(result.events) == 2
        assert result.error_count == 0
        assert result.success_rate == 1.0

    def test_pipeline_counts_normalization_errors(self):
        connector = NormalizationErrorConnector()
        pipeline = NormalizationPipeline(connector)
        result = pipeline.run([{"id": "bad-001"}, {"id": "bad-002"}])
        assert len(result.events) == 0
        assert result.error_count == 2
        assert result.success_rate == 0.0

    def test_pipeline_calls_store_fn_for_each_valid_event(self):
        collected = []
        connector = GoodConnector()
        pipeline = NormalizationPipeline(connector, store_fn=collected.append)
        pipeline.run([{"id": "s1"}, {"id": "s2"}])
        assert len(collected) == 2

    def test_pipeline_empty_input_returns_zero_results(self):
        connector = GoodConnector()
        pipeline = NormalizationPipeline(connector)
        result = pipeline.run([])
        assert result.raw_count == 0
        assert result.events == []


# ── DeduplicationService tests ────────────────────────────────────────────────

class TestDeduplicationService:
    def test_new_event_is_not_duplicate(self):
        svc = DeduplicationService()
        event = _make_event()
        assert not svc.is_duplicate(event)

    def test_same_event_id_is_duplicate_after_mark(self):
        svc = DeduplicationService()
        event = _make_event()
        svc.mark_processed(event)
        assert svc.is_duplicate(event)

    def test_different_entity_id_not_duplicate(self):
        svc = DeduplicationService()
        event_a = _make_event(entity_id="e001")
        event_b = _make_event(entity_id="e002")
        svc.mark_processed(event_a)
        assert not svc.is_duplicate(event_b)

    def test_fuzzy_dedupe_key_generates_stable_hash(self):
        dt = datetime(2026, 4, 1, 10, 30, 0, tzinfo=timezone.utc)
        k1 = DeduplicationService.make_fuzzy_dedupe_key("src", "e1", dt)
        k2 = DeduplicationService.make_fuzzy_dedupe_key("src", "e1", dt)
        assert k1 == k2
        assert k1.startswith("fuzz_")

    def test_in_memory_backend_clear(self):
        backend = InMemoryDeduplicationBackend()
        backend.mark_seen("evt_001")
        assert backend.has_seen("evt_001")
        backend.clear()
        assert not backend.has_seen("evt_001")
