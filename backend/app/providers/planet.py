"""PlanetProvider — commercial daily imagery stub.

Planet Labs provides high-frequency (daily revisit) imagery at 3-5 m
resolution via PlanetScope, and 0.5 m via SkySat.  This stub documents
the integration contract; actual implementation requires a Planet API key.

Resolution: 3-5 m (PlanetScope), 0.5 m (SkySat)
Coverage: Daily global revisit (PlanetScope), tasked (SkySat)
Auth: API key (Basic auth or Bearer token)
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

_ITEM_TYPE = "PSScene"


class PlanetProvider(SatelliteProvider):
    """Planet Labs Data API provider stub."""

    provider_name = "planet"
    display_name = "Planet (PlanetScope)"
    resolution_m = 3  # 3 m PlanetScope; 0.5 m SkySat

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def validate_credentials(self) -> Tuple[bool, str]:
        if not self._settings.planet_api_key:
            return False, "PLANET_API_KEY not set"
        return True, "Planet API key present (not yet verified)"

    def healthcheck(self) -> Tuple[bool, str]:
        """Check Planet Data API reachability."""
        if not self._settings.planet_api_key:
            return False, "PLANET_API_KEY not configured"
        try:
            import httpx

            resp = httpx.get(
                f"{self._settings.planet_api_url}/item-types",
                auth=(self._settings.planet_api_key, ""),
                timeout=10.0,
            )
            resp.raise_for_status()
            return True, "Planet Data API reachable"
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
        if not self._settings.planet_api_key:
            raise ProviderUnavailableError("PLANET_API_KEY not configured")
        try:
            import httpx

            search_filter = {
                "type": "AndFilter",
                "config": [
                    {
                        "type": "GeometryFilter",
                        "field_name": "geometry",
                        "config": geometry,
                    },
                    {
                        "type": "DateRangeFilter",
                        "field_name": "acquired",
                        "config": {
                            "gte": f"{start_date}T00:00:00Z",
                            "lte": f"{end_date}T23:59:59Z",
                        },
                    },
                    {
                        "type": "RangeFilter",
                        "field_name": "cloud_cover",
                        "config": {"lte": cloud_threshold / 100.0},
                    },
                ],
            }
            payload = {
                "item_types": [_ITEM_TYPE],
                "filter": search_filter,
            }
            resp = httpx.post(
                f"{self._settings.planet_api_url}/quick-search",
                json=payload,
                auth=(self._settings.planet_api_key, ""),
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            features = resp.json().get("features", [])[:max_results]
            return [self._normalise(item) for item in features]
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"Planet search failed: {exc}") from exc

    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        if not self._settings.planet_api_key:
            return None
        try:
            import httpx

            resp = httpx.get(
                f"{self._settings.planet_api_url}/item-types/{_ITEM_TYPE}/items/{scene_id}",
                auth=(self._settings.planet_api_key, ""),
                timeout=self._settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return self._normalise(resp.json())
        except Exception as exc:
            log.warning("Planet fetch_scene_metadata failed: %s", exc)
            return None

    def get_capabilities(self) -> Dict[str, Any]:
        caps = super().get_capabilities()
        caps.update({
            "supports_cog_streaming": True,
            "supports_bulk_download": True,
            "requires_credentials": True,
            "item_type": _ITEM_TYPE,
            "daily_revisit": True,
            "commercial": True,
        })
        return caps

    def _normalise(self, item: Dict[str, Any]) -> SceneMetadata:
        props = item.get("properties", {})
        acquired_raw = props.get("acquired", "")
        try:
            acquired_at = datetime.fromisoformat(acquired_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            acquired_at = datetime.utcnow()
        cloud_cover = float(props.get("cloud_cover", 0.0)) * 100.0  # Planet uses 0-1
        raw_assets = item.get("assets", {})
        assets = {}
        for k, v in raw_assets.items():
            if isinstance(v, dict) and v.get("_links", {}).get("_self"):
                assets[k] = v["_links"]["_self"]
        return SceneMetadata(
            scene_id=item.get("id", ""),
            provider=self.provider_name,
            satellite=f"Planet ({props.get('satellite_id', 'PlanetScope')})",
            acquired_at=acquired_at,
            cloud_cover=cloud_cover,
            bbox=_bbox_from_geometry(item.get("geometry")),
            assets=assets,
            geometry=item.get("geometry"),
            raw={"gsd": props.get("gsd", 3.7), "item_type": props.get("item_type", _ITEM_TYPE)},
        )


def _bbox_from_geometry(geom: Optional[Dict[str, Any]]) -> List[float]:
    """Extract bounding box from GeoJSON geometry."""
    if not geom or "coordinates" not in geom:
        return []
    coords = geom["coordinates"]
    if geom["type"] == "Polygon":
        ring = coords[0]
    elif geom["type"] == "MultiPolygon":
        ring = coords[0][0]
    else:
        return []
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return [min(lons), min(lats), max(lons), max(lats)]
