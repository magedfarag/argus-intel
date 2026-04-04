"""USGS LandsatLook STAC connector — V2 BaseConnector implementation.

P1-3.2: Wraps the USGS LandsatLook STAC API (publicly accessible, no auth)
into the V2 BaseConnector interface.  Normalizes items to
``imagery_acquisition`` CanonicalEvents.

connector_id: ``usgs-landsat``
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

_COLLECTION = "landsat-c2l2-sr"
_STAC_URL = "https://landsatlook.usgs.gov/stac-server"
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="allowed",
    redistribution="allowed",
    attribution_required=True,
)


class UsgsLandsatConnector(BaseConnector):
    """USGS LandsatLook STAC — Landsat Collection 2 imagery connector."""

    connector_id = "usgs-landsat"
    display_name = "Landsat (USGS LandsatLook)"
    source_type = "imagery_catalog"

    def __init__(
        self,
        *,
        stac_url: str = _STAC_URL,
        http_timeout: float = 30.0,
    ) -> None:
        self._stac_url = stac_url.rstrip("/")
        self._http_timeout = http_timeout

    def connect(self) -> None:
        """Verify USGS STAC collection is reachable."""
        try:
            resp = httpx.get(
                f"{self._stac_url}/collections/{_COLLECTION}",
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"USGS STAC unreachable: {exc}") from exc

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        *,
        cloud_threshold: float = 20.0,
        max_results: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Search USGS LandsatLook for scenes intersecting an AOI + time window.

        USGS STAC does not support the query extension; cloud filtering is
        done client-side after retrieval.
        """
        dt_range = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
            f"{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        payload: Dict[str, Any] = {
            "collections": [_COLLECTION],
            "intersects": geometry,
            "datetime": dt_range,
            "limit": max_results * 2,  # over-fetch to allow client-side filtering
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
            raise ConnectorUnavailableError(f"USGS STAC search failed: {exc}") from exc

        features = resp.json().get("features", [])

        # Client-side cloud + sort (server does not support query/sortby)
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
        """Convert a raw USGS STAC item to a CanonicalEvent."""
        try:
            return stac_item_to_canonical_event(
                raw,
                connector_id=self.connector_id,
                source="usgs-landsat",
                license_record=_LICENSE,
                raw_source_ref=f"stac://usgs-landsat/{raw.get('id', 'unknown')}",
            )
        except Exception as exc:
            raise NormalizationError(f"USGS item normalization failed: {exc}") from exc

    def health(self) -> ConnectorHealthStatus:
        try:
            resp = httpx.get(
                f"{self._stac_url}/collections/{_COLLECTION}",
                timeout=5.0,
            )
            resp.raise_for_status()
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=True,
                message="USGS STAC reachable",
                last_successful_poll=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
