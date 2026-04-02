from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import httpx
from backend.app.config import AppSettings
from backend.app.models.scene import SceneMetadata
from backend.app.providers.base import ProviderUnavailableError, SatelliteProvider
from backend.app.resilience.retry import with_retry

log = logging.getLogger(__name__)
_COLLECTION = "SENTINEL-2"

class Sentinel2Provider(SatelliteProvider):
    provider_name = "sentinel2"
    display_name  = "Sentinel-2 (Copernicus Data Space)"
    resolution_m  = 10

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - 30:
            return self._token
        resp = httpx.post(
            self._settings.sentinel2_token_url,
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._settings.sentinel2_client_id,
                "client_secret": self._settings.sentinel2_client_secret,
            },
            timeout=self._settings.http_timeout_seconds,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.monotonic() + payload.get("expires_in", 600)
        return self._token

    def validate_credentials(self) -> Tuple[bool, str]:
        if not self._settings.sentinel2_is_configured():
            return False, "SENTINEL2_CLIENT_ID / SENTINEL2_CLIENT_SECRET not set"
        try:
            self._get_token()
            return True, "OAuth2 token obtained"
        except Exception as exc:
            return False, f"Token request failed: {exc}"

    def healthcheck(self) -> Tuple[bool, str]:
        try:
            resp = httpx.get(
                f"{self._settings.sentinel2_stac_url}/collections/{_COLLECTION}",
                headers={"Authorization": f"Bearer {self._get_token()}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return True, "STAC collection reachable"
        except Exception as exc:
            return False, str(exc)

    @with_retry(max_attempts=3, retry_on=(httpx.TimeoutException, httpx.ConnectError))
    def search_imagery(self, geometry, start_date, end_date, cloud_threshold=20.0, max_results=10):
        try:
            token = self._get_token()
        except Exception as exc:
            raise ProviderUnavailableError(f"Sentinel-2 auth failed: {exc}") from exc
        payload = {
            "collections": [_COLLECTION],
            "intersects":  geometry,
            "datetime":    f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
            "limit":       max_results,
            "query":       {"eo:cloud_cover": {"lte": cloud_threshold}},
            "sortby":      [{"field": "datetime", "direction": "desc"}],
        }
        resp = httpx.post(
            f"{self._settings.sentinel2_stac_url}/search",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=self._settings.http_timeout_seconds,
        )
        resp.raise_for_status()
        return [self._normalise(item) for item in resp.json().get("features", [])]

    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        try:
            token = self._get_token()
            resp = httpx.get(
                f"{self._settings.sentinel2_stac_url}/collections/{_COLLECTION}/items/{scene_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return self._normalise(resp.json())
        except Exception as exc:
            log.warning("fetch_scene_metadata failed: %s", exc)
            return None

    def get_capabilities(self):
        caps = super().get_capabilities()
        caps.update({"supports_cog_streaming": True, "requires_credentials": True, "collection": _COLLECTION})
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
        band_map = {
            "B04": "B04", "red": "B04", "B08": "B08", "nir": "B08",
            "B11": "B11", "swir16": "B11", "B03": "B03", "green": "B03",
            "B02": "B02", "blue": "B02", "SCL": "SCL", "scl": "SCL",
            "TCI": "TCI", "visual": "TCI",
        }
        assets = {band_map.get(k, k): v.get("href", "") for k, v in raw_assets.items() if v.get("href")}
        return SceneMetadata(
            scene_id=item.get("id", ""), provider=self.provider_name, satellite="Sentinel-2",
            acquired_at=acquired_at, cloud_cover=cloud_cover, bbox=item.get("bbox", []),
            assets=assets, geometry=item.get("geometry"),
            raw={"mgrs_tile": props.get("s2:mgrs_tile", "")},
        )
