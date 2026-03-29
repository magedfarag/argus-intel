"""MaxarProvider — commercial high-resolution imagery stub.

Maxar (formerly DigitalGlobe) provides sub-metre resolution imagery via
SecureWatch / GEGD API.  This stub documents the integration contract;
actual implementation requires a Maxar SecureWatch subscription.

Resolution: 0.3-0.5 m (WorldView-3/4), 0.5 m (GeoEye-1)
Coverage: Tasked by request; archive search via STAC-like API
Auth: API key + OAuth2 client credentials
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import AppSettings
from backend.app.models.scene import SceneMetadata
from backend.app.providers.base import ProviderUnavailableError, SatelliteProvider
from backend.app.resilience.retry import with_retry

log = logging.getLogger(__name__)

_COLLECTION = "maxar-open-data"


class MaxarProvider(SatelliteProvider):
    """Maxar SecureWatch / Open Data STAC provider stub."""

    provider_name = "maxar"
    display_name = "Maxar (SecureWatch)"
    resolution_m = 0  # 0.3-0.5 m — sub-metre

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def validate_credentials(self) -> Tuple[bool, str]:
        if not self._settings.maxar_api_key:
            return False, "MAXAR_API_KEY not set"
        return True, "Maxar API key present (not yet verified)"

    def healthcheck(self) -> Tuple[bool, str]:
        """Lightweight STAC endpoint probe."""
        if not self._settings.maxar_api_key:
            return False, "MAXAR_API_KEY not configured"
        try:
            import httpx

            resp = httpx.get(
                f"{self._settings.maxar_stac_url}/collections/{_COLLECTION}",
                headers={"Authorization": f"Bearer {self._settings.maxar_api_key}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return True, "Maxar STAC reachable"
        except Exception as exc:
            return False, str(exc)

    @with_retry(max_attempts=3)
    def search_imagery(
        self,
        geometry: Dict[str, Any],
        start_date: str,
        end_date: str,
        cloud_threshold: float = 20.0,
        max_results: int = 10,
    ) -> List[SceneMetadata]:
        if not self._settings.maxar_api_key:
            raise ProviderUnavailableError("MAXAR_API_KEY not configured")
        try:
            import httpx

            payload = {
                "collections": [_COLLECTION],
                "intersects": geometry,
                "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
                "limit": max_results,
                "query": {"eo:cloud_cover": {"lte": cloud_threshold}},
                "sortby": [{"field": "datetime", "direction": "desc"}],
            }
            resp = httpx.post(
                f"{self._settings.maxar_stac_url}/search",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._settings.maxar_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return [self._normalise(item) for item in resp.json().get("features", [])]
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"Maxar STAC search failed: {exc}") from exc

    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        if not self._settings.maxar_api_key:
            return None
        try:
            import httpx

            resp = httpx.get(
                f"{self._settings.maxar_stac_url}/collections/{_COLLECTION}/items/{scene_id}",
                headers={"Authorization": f"Bearer {self._settings.maxar_api_key}"},
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return self._normalise(resp.json())
        except Exception as exc:
            log.warning("Maxar fetch_scene_metadata failed: %s", exc)
            return None

    def get_capabilities(self) -> Dict[str, Any]:
        caps = super().get_capabilities()
        caps.update({
            "supports_cog_streaming": True,
            "supports_bulk_download": True,
            "requires_credentials": True,
            "collection": _COLLECTION,
            "max_resolution_m": 0.3,
            "commercial": True,
        })
        return caps

    def _normalise(self, item: Dict[str, Any]) -> SceneMetadata:
        props = item.get("properties", {})
        acquired_raw = props.get("datetime") or props.get("start_datetime", "")
        try:
            acquired_at = datetime.fromisoformat(acquired_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            acquired_at = datetime.utcnow()
        cloud_cover = float(props.get("eo:cloud_cover", 0.0))
        raw_assets = item.get("assets", {})
        assets = {k: v.get("href", "") for k, v in raw_assets.items() if v.get("href")}
        return SceneMetadata(
            scene_id=item.get("id", ""),
            provider=self.provider_name,
            satellite=f"Maxar ({props.get('platform', 'unknown')})",
            acquired_at=acquired_at,
            cloud_cover=cloud_cover,
            bbox=item.get("bbox", []),
            assets=assets,
            geometry=item.get("geometry"),
            raw={"gsd": props.get("gsd", 0.5)},
        )
