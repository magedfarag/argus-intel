"""Connector registry — priority-ordered, circuit-breaker-aware.

P0-6.2: Extends the existing ProviderRegistry pattern into a generic
connector registry that supports any source family.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from src.connectors.base import BaseConnector, ConnectorHealthStatus, ConnectorUnavailableError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Manages all registered connectors and their availability state.

    Connectors are stored in registration order (priority = order of registration).
    Circuit-breaker integration is additive: callers wrap fetch() independently.
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, BaseConnector] = {}
        self._disabled: set[str] = set()

    def register(self, connector: BaseConnector) -> None:
        """Register a connector instance.  Calls connect() and logs any failures."""
        cid = connector.connector_id
        try:
            connector.connect()
            self._connectors[cid] = connector
            logger.info("Connector registered: %s (%s)", cid, connector.display_name)
        except ConnectorUnavailableError as exc:
            logger.warning("Connector %s unavailable at startup — registered but disabled: %s", cid, exc)
            self._connectors[cid] = connector
            self._disabled.add(cid)
        except Exception as exc:  # noqa: BLE001
            logger.error("Connector %s failed to connect — not registered: %s", cid, exc, exc_info=True)

    def get(self, connector_id: str) -> Optional[BaseConnector]:
        """Return connector by id, or None if not found / disabled."""
        c = self._connectors.get(connector_id)
        if c and connector_id not in self._disabled:
            return c
        return None

    def all_connectors(self, include_disabled: bool = False) -> List[BaseConnector]:
        """Return all registered connectors, optionally including disabled ones."""
        if include_disabled:
            return list(self._connectors.values())
        return [c for cid, c in self._connectors.items() if cid not in self._disabled]

    def connectors_by_source_type(self, source_type: str) -> List[BaseConnector]:
        """Return enabled connectors filtered by source_type."""
        return [c for c in self.all_connectors() if c.source_type == source_type]

    def is_available(self, connector_id: str) -> bool:
        return connector_id in self._connectors and connector_id not in self._disabled

    def disable(self, connector_id: str) -> None:
        """Temporarily disable a connector (e.g. after circuit-breaker open)."""
        self._disabled.add(connector_id)
        logger.warning("Connector disabled: %s", connector_id)

    def enable(self, connector_id: str) -> None:
        """Re-enable a previously disabled connector."""
        self._disabled.discard(connector_id)
        logger.info("Connector re-enabled: %s", connector_id)

    def health_snapshot(self) -> Dict[str, ConnectorHealthStatus]:
        """Return health status for all registered connectors."""
        result: Dict[str, ConnectorHealthStatus] = {}
        for cid, connector in self._connectors.items():
            try:
                result[cid] = connector.health()
            except Exception as exc:  # noqa: BLE001
                result[cid] = ConnectorHealthStatus(
                    connector_id=cid,
                    healthy=False,
                    message=f"health() raised: {exc}",
                )
        return result
