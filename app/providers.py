"""Legacy provider stubs - DEPRECATED.

New code should import from the backend.app.providers package:
    from backend.app.providers.sentinel2 import Sentinel2Provider
    from backend.app.providers.landsat import LandsatProvider
"""
from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "backend.app.providers (legacy module) is deprecated. "
    "Import from backend.app.providers package instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export under old stub names for backward compatibility
from app.providers.sentinel2 import Sentinel2Provider as Sentinel2StacProvider  # noqa: F401,E402
from app.providers.landsat import LandsatProvider as LandsatStacProvider        # noqa: F401,E402


class LandsatStacProvider(BaseImageryProvider):
    provider_name = 'landsat-stac'

    def search_scenes(self, params: SearchParams) -> List[Dict[str, Any]]:
        # Intended integration target:
        # LandsatLook or USGS M2M / STAC search for matching scenes.
        return []
