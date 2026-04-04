"""Abstract base connector — the extension point for every data source.

P0-6.1: Extends the existing SatelliteProvider ABC pattern into a generic
connector that any source family (imagery, telemetry, records, context) can
implement.

Every concrete connector MUST implement: connect(), fetch(), normalize(), health().
Optional overrides: backoff_policy(), quota_status().
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.models.canonical_event import CanonicalEvent

logger = logging.getLogger(__name__)


@dataclass
class ConnectorHealthStatus:
    """Health snapshot returned by BaseConnector.health()."""
    connector_id: str
    healthy: bool
    message: str
    last_successful_poll: Optional[datetime] = None
    error_count: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


class ConnectorError(Exception):
    """Raised for unrecoverable connector failures."""


class ConnectorUnavailableError(ConnectorError):
    """Raised when the remote source is temporarily unavailable."""


class NormalizationError(Exception):
    """Raised when a raw record cannot be transformed into a CanonicalEvent."""


class BaseConnector(ABC):
    """Common interface every data source connector must implement.

    Design constraints:
    - normalize() is pure: it must not perform I/O.
    - connect() / fetch() may be async-wrapped by callers; keep them
      synchronous here and override in async subclasses when needed.
    - health() must be lightweight (no heavy queries, no full fetches).
    """

    #: Short slug used in logs, metrics, and canonical event source field.
    connector_id: str = "base"
    #: Human-readable name for UI source catalogs.
    display_name: str = "Base Connector"
    #: SourceType string; must match SourceType enum values.
    source_type: str = "derived"

    @abstractmethod
    def connect(self) -> None:
        """Establish / verify connectivity to the remote source.

        Should be called once at startup by the ConnectorRegistry.
        Raise ConnectorUnavailableError if the source is unreachable.
        """

    @abstractmethod
    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve raw records from the source for the given AOI + time window.

        Returns:
            A list of raw dicts; each will be passed to normalize().

        Raises:
            ConnectorUnavailableError: if the source is temporarily down.
            ConnectorError: for unrecoverable failures.
        """

    @abstractmethod
    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Transform a single raw record into a CanonicalEvent.

        Must be pure (no I/O). Raise NormalizationError if the record
        cannot be transformed.
        """

    @abstractmethod
    def health(self) -> ConnectorHealthStatus:
        """Return a lightweight health snapshot for dashboards and alerting."""

    # ── Optional overrides ────────────────────────────────────────────────────

    def quota_status(self) -> Dict[str, Any]:
        """Return current quota / rate-limit information.  Override if relevant."""
        return {"available": True, "note": "quota tracking not implemented"}

    def fetch_and_normalize(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> Tuple[List[CanonicalEvent], List[str]]:
        """Convenience: fetch raw records, normalize each, collect warnings.

        Returns:
            (canonical_events, warning_strings) — warnings include per-record
            normalization errors so callers can log without aborting.
        """
        raws = self.fetch(geometry, start_time, end_time, **kwargs)
        events: List[CanonicalEvent] = []
        warnings: List[str] = []
        for raw in raws:
            try:
                events.append(self.normalize(raw))
            except NormalizationError as exc:
                warnings.append(f"normalization skipped: {exc}")
                logger.warning("[%s] normalization skipped: %s", self.connector_id, exc)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"unexpected normalization error: {exc}")
                logger.error("[%s] unexpected normalization error: %s", self.connector_id, exc, exc_info=True)
        return events, warnings
