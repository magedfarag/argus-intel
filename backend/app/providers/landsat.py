from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import httpx
from backend.app.config import AppSettings
from backend.app.models.scene import SceneMetadata
from backend.app.providers.base import ProviderUnavailableError, SatelliteProvider
from backend.app.resilience.retry import with_retry

log = logging.getLogger(__name__)
_COLLECTION = "landsat-c2l2-sr"
_SATELLITES = {"LANDSAT_9": "Landsat-9", "LANDSAT_8": "Landsat-8", "LANDSAT_7": "Landsat-7"}

class LandsatProvider(SatelliteProvider):
    provider_name = "landsat"
    display_name  = "Landsat (USGS LandsatLook)"
    resolution_m  = 30

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def validate_credentials(self) -> Tuple[bool, str]:
        return True, "Landsat STAC is publicly accessible"

    def healthcheck(self) -> Tuple[bool, str]:
        try:
            resp = httpx.get(f"{self._settings.landsat_stac_url}/collections/{_COLLECTION}", timeout=10.0)
            resp.raise_for_status()
            return True, "USGS STAC reachable"
        except Exception as exc:
            return False, str(exc)

    @with_retry(max_attempts=3)
    def search_imagery(self, geometry, start_date, end_date, cloud_threshold=20.0, max_results=10):
        payload = {
            "collections": [_COLLECTION],
            "intersects":  geometry,
            "datetime":    f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
            "limit":       max_results,
        }
        try:
            resp = httpx.post(
                f"{self._settings.landsat_stac_url}/search",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"USGS STAC unreachable: {exc}") from exc
        features = resp.json().get("features", [])
        # Post-filter by cloud cover (USGS STAC doesn't support query extension)
        filtered = [
            f for f in features
            if float(f.get("properties", {}).get("eo:cloud_cover", 100.0)) <= cloud_threshold
        ]
        # Sort by datetime descending
        filtered.sort(
            key=lambda f: f.get("properties", {}).get("datetime", ""),
            reverse=True,
        )
        return [self._normalise(item) for item in filtered[:max_results]]

    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        try:
            resp = httpx.get(
                f"{self._settings.landsat_stac_url}/collections/{_COLLECTION}/items/{scene_id}",
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return self._normalise(resp.json())
        except Exception as exc:
            log.warning("fetch_scene_metadata failed: %s", exc)
            return None

    def get_capabilities(self):
        caps = super().get_capabilities()
        caps.update({"supports_cog_streaming": True, "requires_credentials": False, "collection": _COLLECTION})
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
            "red": "B4", "SR_B4": "B4", "nir08": "B5", "SR_B5": "B5",
            "swir16": "B6", "SR_B6": "B6", "blue": "B2", "SR_B2": "B2",
            "green": "B3", "SR_B3": "B3", "qa_pixel": "QA_PIXEL",
            "thumbnail": "thumbnail",
        }
        assets = {band_map.get(k, k): v.get("href", "") for k, v in raw_assets.items() if v.get("href")}
        satellite_id = props.get("landsat:satellite_id", "")
        return SceneMetadata(
            scene_id=item.get("id", ""), provider=self.provider_name,
            satellite=_SATELLITES.get(satellite_id, f"Landsat ({satellite_id})"),
            acquired_at=acquired_at, cloud_cover=cloud_cover, bbox=item.get("bbox", []),
            assets=assets, geometry=item.get("geometry"),
            raw={"path": props.get("landsat:wrs_path", ""), "row": props.get("landsat:wrs_row", "")},
        )
