"""Normalised scene metadata shared across all satellite providers."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SceneMetadata:
    """Provider-agnostic representation of a single satellite scene."""

    scene_id: str
    provider: str          # e.g. sentinel2, landsat, demo
    satellite: str         # e.g. Sentinel-2B, Landsat-9
    acquired_at: datetime
    cloud_cover: float     # 0-100 percent
    bbox: List[float]      # [min_lon, min_lat, max_lon, max_lat]
    # Asset download URLs keyed by band name (B04, B08, QA_PIXEL, SCL ...)
    assets: Dict[str, str] = field(default_factory=dict)
    # STAC item geometry (GeoJSON-like dict, Polygon)
    geometry: Optional[Dict[str, Any]] = None
    # Fractional AOI overlap 0-1 (filled by scene_selection service)
    aoi_overlap: float = 0.0
    # Provider-specific raw properties (not exposed to API consumers)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def resolution_m(self) -> int:
        """Nominal spatial resolution in metres for the primary bands."""
        if self.provider == "sentinel2":
            return 10
        if self.provider == "landsat":
            return 30
        return 0
