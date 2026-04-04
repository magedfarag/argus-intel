"""Sentinel-2 CDSE STAC connector — V2 BaseConnector implementation.

P1-3.1: Wraps the Copernicus Data Space Ecosystem STAC search into the
V2 BaseConnector interface.  OAuth2 client_credentials auth is used for
the CDSE endpoint; anonymous access is used for public Element84 endpoints.

connector_id: ``cdse-sentinel2``
source_type:  ``imagery_catalog``
"""
from __future__ import annotations

import logging
import time
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

_COLLECTION = "sentinel-2-l2a"
_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE"
    "/protocol/openid-connect/token"
)
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)


class CdseSentinel2Connector(BaseConnector):
    """Copernicus Data Space Ecosystem — Sentinel-2 STAC connector."""

    connector_id = "cdse-sentinel2"
    display_name = "Sentinel-2 (Copernicus Data Space)"
    source_type = "imagery_catalog"

    def __init__(
        self,
        *,
        stac_url: str = _STAC_URL,
        token_url: str = _TOKEN_URL,
        client_id: str = "",
        client_secret: str = "",
        http_timeout: float = 30.0,
    ) -> None:
        self._stac_url = stac_url.rstrip("/")
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_timeout = http_timeout
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ── Auth ──────────────────────────────────────────────────────────────────

    @property
    def _needs_auth(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def _get_token(self) -> str:
        if not self._needs_auth:
            return ""
        if self._token and time.monotonic() < self._token_expiry - 30:
            return self._token
        try:
            resp = httpx.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"CDSE token request failed: {exc}") from exc
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.monotonic() + payload.get("expires_in", 600)
        return self._token

    def _auth_headers(self) -> Dict[str, str]:
        token = self._get_token()
        if token:
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    # ── BaseConnector interface ───────────────────────────────────────────────

    def connect(self) -> None:
        """Verify STAC collection is reachable (and get a token if auth configured)."""
        if self._needs_auth:
            self._get_token()  # raises ConnectorUnavailableError on failure
        try:
            headers = self._auth_headers() if self._needs_auth else {}
            resp = httpx.get(
                f"{self._stac_url}/collections/{_COLLECTION}",
                headers=headers,
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"CDSE STAC unreachable: {exc}") from exc

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
        """Search CDSE STAC for Sentinel-2 scenes intersecting an AOI + time window."""
        if self._needs_auth:
            self._get_token()

        dt_range = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
            f"{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        payload: Dict[str, Any] = {
            "collections": [_COLLECTION],
            "intersects": geometry,
            "datetime": dt_range,
            "limit": max_results,
            "query": {"eo:cloud_cover": {"lte": cloud_threshold}},
            "sortby": [{"field": "datetime", "direction": "desc"}],
        }
        try:
            resp = httpx.post(
                f"{self._stac_url}/search",
                json=payload,
                headers=self._auth_headers(),
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"CDSE STAC search failed: {exc}") from exc

        return resp.json().get("features", [])

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Convert a raw CDSE STAC item to a CanonicalEvent."""
        try:
            return stac_item_to_canonical_event(
                raw,
                connector_id=self.connector_id,
                source="copernicus-cdse",
                license_record=_LICENSE,
                raw_source_ref=f"stac://copernicus-cdse/{raw.get('id', 'unknown')}",
            )
        except Exception as exc:
            raise NormalizationError(f"CDSE item normalization failed: {exc}") from exc

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
                message="CDSE STAC reachable",
                last_successful_poll=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
