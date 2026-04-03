"""Normalization pipeline: raw payload → parse → validate → CanonicalEvent → store.

P0-6.3: The pipeline captures raw payloads, drives connector-specific parsing,
validates the resulting CanonicalEvent, and emits results with any per-record
warnings so callers can audit quality without aborting ingestion.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from src.connectors.base import BaseConnector, NormalizationError
from src.models.canonical_event import CanonicalEvent

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """The outcome of running a batch of raw records through the pipeline."""
    events: List[CanonicalEvent] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_count: int = 0
    raw_count: int = 0

    @property
    def success_rate(self) -> float:
        if self.raw_count == 0:
            return 1.0
        return (self.raw_count - self.error_count) / self.raw_count


class NormalizationPipeline:
    """Orchestrates raw → CanonicalEvent transformation for a single connector.

    Usage::
        pipeline = NormalizationPipeline(connector)
        result = pipeline.run(raw_records)

    The pipeline:
    1. Captures raw record reference for provenance.
    2. Calls connector.normalize(raw).
    3. Validates the returned CanonicalEvent via Pydantic.
    4. Passes validated events to the optional store_fn callback.
    5. Collects all warnings and errors without aborting on individual failures.
    """

    def __init__(
        self,
        connector: BaseConnector,
        store_fn: Optional[Callable[[CanonicalEvent], None]] = None,
    ) -> None:
        self._connector = connector
        self._store_fn = store_fn

    def run(self, raw_records: List[Dict[str, Any]]) -> PipelineResult:
        """Process a batch of raw records and return aggregated results."""
        result = PipelineResult(raw_count=len(raw_records))
        for raw in raw_records:
            try:
                event = self._connector.normalize(raw)
                # Validate via Pydantic (model_validate enforces all constraints)
                validated = CanonicalEvent.model_validate(event.model_dump())
                if self._store_fn:
                    self._store_fn(validated)
                result.events.append(validated)
            except (NormalizationError, ValidationError) as exc:
                result.error_count += 1
                msg = f"[{self._connector.connector_id}] record skipped: {exc}"
                result.warnings.append(msg)
                logger.warning(msg)
            except Exception as exc:  # noqa: BLE001
                result.error_count += 1
                msg = f"[{self._connector.connector_id}] unexpected error: {exc}"
                result.warnings.append(msg)
                logger.error(msg, exc_info=True)
        logger.info(
            "Pipeline finished | connector=%s total=%d ok=%d errors=%d",
            self._connector.connector_id,
            result.raw_count,
            len(result.events),
            result.error_count,
        )
        return result
