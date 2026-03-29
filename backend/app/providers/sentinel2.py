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
_COLLECTION_CDSE = "SENTINEL-2"
_COLLECTION_E84  = "sentinel-2-l2a"

class Sentinel2Provider(SatelliteProvider):
    provider_name = "sentinel2"
    resolution_m  = 10

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    @property
    def _is_element84(self) -> bool:
        return "element84.com" in self._settings.sentinel2_stac_url

    @property
    def _collection(self) -> str:
        return _COLLECTION_E84 if self._is_element84 else _COLLECTION_CDSE

    @property
    def display_name(self) -> str:
        if self._is_element84:
            return "Sentinel-2 (Element84 Earth Search)"
        return "Sentinel-2 (Copernicus Data Space)"

    def _auth_headers(self) -> Dict[str, str]:
        if self._is_element84:
            return {"Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def _get_token(self) -> str:
        if self._is_element84:
            return ""
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
        if self._is_element84:
            return True, "Element84 Earth Search is publicly accessible"
        if not self._settings.sentinel2_is_configured():
            return False, "SENTINEL2_CLIENT_ID / SENTINEL2_CLIENT_SECRET not set"
        try:
            self._get_token()
            return True, "OAuth2 token obtained"
        except Exception as exc:
            return False, f"Token request failed: {exc}"

    def healthcheck(self) -> Tuple[bool, str]:
        try:
            headers = {} if self._is_element84 else self._auth_headers()
            resp = httpx.get(
                f"{self._settings.sentinel2_stac_url}/collections/{self._collection}",
                headers=headers,
                timeout=10.0,
            )
            resp.raise_for_status()
            return True, "STAC collection reachable"
        except Exception as exc:
            return False, str(exc)

    @with_retry(max_attempts=3)
    def search_imagery(self, geometry, start_date, end_date, cloud_threshold=20.0, max_results=10):
        if not self._is_element84:
            try:
                self._get_token()
            except Exception as exc:
                raise ProviderUnavailableError(f"Sentinel-2 auth failed: {exc}") from exc
        payload = {
            "collections": [self._collection],
            "intersects":  geometry,
            "datetime":    f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
            "limit":       max_results,
        }
        # CDSE supports query/sortby extensions; Element84 does not (returns 400)
        if not self._is_element84:
            payload["query"] = {"eo:cloud_cover": {"lte": cloud_threshold}}
            payload["sortby"] = [{"field": "datetime", "direction": "desc"}]
        resp = httpx.post(
            f"{self._settings.sentinel2_stac_url}/search",
            json=payload,
            headers=self._auth_headers(),
            timeout=self._settings.http_timeout_seconds,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        # Post-filter and sort for Element84 (no server-side query/sortby)
        if self._is_element84:
            features = [
                f for f in features
                if float(f.get("properties", {}).get("eo:cloud_cover", 100.0)) <= cloud_threshold
            ]
            features.sort(
                key=lambda f: f.get("properties", {}).get("datetime", ""),
                reverse=True,
            )
        return [self._normalise(item) for item in features[:max_results]]

    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        try:
            resp = httpx.get(
                f"{self._settings.sentinel2_stac_url}/collections/{self._collection}/items/{scene_id}",
                headers=self._auth_headers(),
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return self._normalise(resp.json())
        except Exception as exc:
            log.warning("fetch_scene_metadata failed: %s", exc)
            return None

    def get_capabilities(self):
        caps = super().get_capabilities()
        caps.update({
            "supports_cog_streaming": True,
            "requires_credentials": not self._is_element84,
            "collection": self._collection,
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
        band_map = {
            "B04": "B04", "red": "B04", "B08": "B08", "nir": "B08",
            "nir08": "B8A",
            "B11": "B11", "swir16": "B11", "B03": "B03", "green": "B03",
            "B02": "B02", "blue": "B02", "SCL": "SCL", "scl": "SCL",
            "TCI": "TCI", "visual": "TCI",
            "thumbnail": "thumbnail",
        }
        assets = {band_map.get(k, k): v.get("href", "") for k, v in raw_assets.items() if v.get("href")}
        return SceneMetadata(
            scene_id=item.get("id", ""), provider=self.provider_name, satellite="Sentinel-2",
            acquired_at=acquired_at, cloud_cover=cloud_cover, bbox=item.get("bbox", []),
            assets=assets, geometry=item.get("geometry"),
            raw={"mgrs_tile": props.get("s2:mgrs_tile", props.get("grid:code", ""))},
        )
