"""Microsoft Planetary Computer STAC connector.

P1-3.4: Adds the Microsoft Planetary Computer public STAC catalog as a V2
BaseConnector.  The catalog is publicly browsable; a subscription key may
be set for higher rate limits and signed asset URLs.

connector_id: ``planetary-computer``
source_type:  ``imagery_catalog``

Reference: https://planetarycomputer.microsoft.com/api/stac/v1
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

_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
_DEFAULT_COLLECTIONS = [
    "sentinel-2-l2a",
    "landsat-c2-l2",
    "sentinel-1-rtc",
]
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)


class PlanetaryComputerConnector(BaseConnector):
    """Microsoft Planetary Computer — multi-collection STAC connector."""

    connector_id = "planetary-computer"
    display_name = "Planetary Computer (Microsoft)"
    source_type = "imagery_catalog"

    def __init__(
        self,
        *,
        stac_url: str = _STAC_URL,
        subscription_key: str = "",
        collections: Optional[List[str]] = None,
        http_timeout: float = 30.0,
    ) -> None:
        self._stac_url = stac_url.rstrip("/")
        self._subscription_key = subscription_key
        self._collections = collections or _DEFAULT_COLLECTIONS
        self._http_timeout = http_timeout

    def _request_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._subscription_key:
            headers["Ocp-Apim-Subscription-Key"] = self._subscription_key
        return headers

    def connect(self) -> None:
        """Verify Planetary Computer STAC landing page is reachable."""
        try:
            resp = httpx.get(
                self._stac_url,
                headers=self._request_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(
                f"Planetary Computer unreachable: {exc}"
            ) from exc

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
        """Search Planetary Computer across configured collections for AOI + time window."""
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
                headers=self._request_headers(),
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(
                f"Planetary Computer search failed: {exc}"
            ) from exc

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
        """Convert a raw Planetary Computer STAC item to a CanonicalEvent."""
        collection = raw.get("collection", "")
        source = f"planetary-computer:{collection}" if collection else "planetary-computer"
        try:
            return stac_item_to_canonical_event(
                raw,
                connector_id=self.connector_id,
                source=source,
                license_record=_LICENSE,
                raw_source_ref=f"stac://planetary-computer/{raw.get('id', 'unknown')}",
            )
        except Exception as exc:
            raise NormalizationError(
                f"Planetary Computer item normalization failed: {exc}"
            ) from exc

    def health(self) -> ConnectorHealthStatus:
        try:
            resp = httpx.get(
                self._stac_url,
                headers=self._request_headers(),
                timeout=5.0,
            )
            resp.raise_for_status()
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=True,
                message="Planetary Computer STAC reachable",
                last_successful_poll=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
