"""Element 84 Earth Search STAC connector.

P1-3.3: Adds the Element84 Earth Search public STAC catalog as a V2
BaseConnector.  Earth Search hosts multiple Sentinel-2, Landsat, and
other collections without any authentication requirement.

connector_id: ``earth-search``
source_type:  ``imagery_catalog``
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    ConnectorUnavailableError,
    NormalizationError,
)
from src.connectors.stac_normalizer import stac_item_to_canonical_event
from src.models.canonical_event import CanonicalEvent, LicenseRecord

logger = logging.getLogger(__name__)

_STAC_URL = "https://earth-search.aws.element84.com/v1"
# Primary collections to include in multi-collection searches
_DEFAULT_COLLECTIONS = [
    "sentinel-2-l2a",
    "landsat-c2-l2",
]
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)


class EarthSearchConnector(BaseConnector):
    """Element 84 Earth Search — multi-collection STAC connector."""

    connector_id = "earth-search"
    display_name = "Earth Search (Element 84)"
    source_type = "imagery_catalog"

    def __init__(
        self,
        *,
        stac_url: str = _STAC_URL,
        collections: Optional[List[str]] = None,
        http_timeout: float = 30.0,
    ) -> None:
        self._stac_url = stac_url.rstrip("/")
        self._collections = collections or _DEFAULT_COLLECTIONS
        self._http_timeout = http_timeout

    def connect(self) -> None:
        """Verify Earth Search landing page is reachable."""
        try:
            resp = httpx.get(self._stac_url, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"Earth Search unreachable: {exc}") from exc

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        *,
        cloud_threshold: float = 20.0,
        max_results: int = 20,
        collections: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Search Earth Search across configured collections for an AOI + time window.

        Earth Search does not support the STAC query extension; cloud filtering
        and sorting are done client-side.
        """
        active_collections = collections or self._collections
        dt_range = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
            f"{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        payload: Dict[str, Any] = {
            "collections": active_collections,
            "intersects": geometry,
            "datetime": dt_range,
            "limit": max_results * 2,
        }
        try:
            resp = httpx.post(
                f"{self._stac_url}/search",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"Earth Search request failed: {exc}") from exc

        features = resp.json().get("features", [])
        filtered = [
            f for f in features
            if float(f.get("properties", {}).get("eo:cloud_cover", 100.0)) <= cloud_threshold
        ]
        filtered.sort(
            key=lambda f: f.get("properties", {}).get("datetime", ""),
            reverse=True,
        )
        return filtered[:max_results]

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Convert a raw Earth Search STAC item to a CanonicalEvent."""
        collection = raw.get("collection", "")
        source = f"earth-search:{collection}" if collection else "earth-search"
        try:
            return stac_item_to_canonical_event(
                raw,
                connector_id=self.connector_id,
                source=source,
                license_record=_LICENSE,
                raw_source_ref=f"stac://earth-search/{raw.get('id', 'unknown')}",
            )
        except Exception as exc:
            raise NormalizationError(f"Earth Search item normalization failed: {exc}") from exc

    def health(self) -> ConnectorHealthStatus:
        try:
            resp = httpx.get(self._stac_url, timeout=5.0)
            resp.raise_for_status()
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=True,
                message="Earth Search reachable",
                last_successful_poll=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
