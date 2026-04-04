"""Satellite scene thumbnail generation service.

Generates PNG thumbnail crops from Cloud Optimized GeoTIFF (COG) scenes
using rasterio.  When rasterio is not installed, the service gracefully
degrades — returning ``None`` so callers can fall back to placeholders.

Thumbnails are cached in an LRU dict keyed by (scene_id, bbox_hash) so
repeated requests for the same crop are served from memory.
"""
from __future__ import annotations

import hashlib
import io
import logging
from collections import OrderedDict
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

_THUMBNAIL_SIZE: Tuple[int, int] = (256, 256)
_MAX_CACHE_ENTRIES = 128


def _rasterio_available() -> bool:
    try:
        import rasterio  # noqa: F401
        return True
    except ImportError:
        return False


class ThumbnailCache:
    """Simple bounded LRU cache for generated thumbnail bytes."""

    def __init__(self, max_entries: int = _MAX_CACHE_ENTRIES) -> None:
        self._store: OrderedDict[str, bytes] = OrderedDict()
        self._max = max_entries

    def get(self, key: str) -> Optional[bytes]:
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, key: str, data: bytes) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        else:
            if len(self._store) >= self._max:
                self._store.popitem(last=False)
        self._store[key] = data

    @property
    def size(self) -> int:
        return len(self._store)


# Module-level singleton
_cache = ThumbnailCache()


def cache_key(scene_id: str, bbox: List[float]) -> str:
    """Deterministic cache key from scene ID and bounding box."""
    bbox_str = ",".join(f"{v:.6f}" for v in bbox)
    raw = f"{scene_id}:{bbox_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_thumbnail(
    scene_url: str,
    bbox: List[float],
    scene_id: str,
    size: Tuple[int, int] = _THUMBNAIL_SIZE,
    bearer_token: Optional[str] = None,
) -> Optional[bytes]:
    """Generate a PNG thumbnail from a COG scene URL, cropped to bbox.

    Parameters
    ----------
    scene_url:
        HTTPS URL to a Cloud Optimized GeoTIFF.
    bbox:
        [min_lon, min_lat, max_lon, max_lat] in EPSG:4326.
    scene_id:
        Unique scene identifier (used for cache key).
    size:
        (width, height) of the output thumbnail in pixels.
    bearer_token:
        Optional OAuth2 bearer token for authenticated COG access.

    Returns
    -------
    PNG bytes or ``None`` if rasterio is unavailable or an error occurs.
    """
    key = cache_key(scene_id, bbox)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    if not _rasterio_available():
        log.debug("rasterio not available — skipping thumbnail generation")
        return None

    try:
        import numpy as np
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds

        env_kwargs = {}
        if bearer_token:
            env_kwargs["GDAL_HTTP_BEARER"] = bearer_token
            env_kwargs["GDAL_HTTP_AUTH"] = "BEARER"

        with rasterio.Env(**env_kwargs), rasterio.open(scene_url) as src:
            # Reproject bbox from WGS84 to scene CRS if needed
            src_crs = src.crs
            wgs84 = CRS.from_epsg(4326)
            bounds = list(bbox)
            if src_crs and src_crs != wgs84:
                bounds = list(transform_bounds(wgs84, src_crs, *bbox))
            window = from_bounds(*bounds, transform=src.transform)
            # Clamp window to dataset bounds
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
            # Read RGB bands (1, 2, 3) or as many as available
            band_count = min(src.count, 3)
            data = src.read(
                list(range(1, band_count + 1)),
                window=window,
                out_shape=(band_count, size[1], size[0]),
            )

            # Normalise to 0-255 uint8
            data = data.astype(np.float32)
            for i in range(band_count):
                band = data[i]
                p2, p98 = np.percentile(band[band > 0], (2, 98)) if (band > 0).any() else (0, 1)
                if p98 > p2:
                    band = np.clip((band - p2) / (p98 - p2) * 255, 0, 255)
                data[i] = band
            data = data.astype(np.uint8)

            # Encode as PNG using PIL if available, else raw bytes
            png_bytes = _encode_png(data, size)
            if png_bytes:
                _cache.put(key, png_bytes)
            return png_bytes

    except Exception as exc:
        log.warning("Thumbnail generation failed for %s: %s", scene_id, exc)
        return None


def _encode_png(data, size: Tuple[int, int]) -> Optional[bytes]:
    """Encode numpy array to PNG bytes."""
    try:
        from PIL import Image

        bands = data.shape[0]
        if bands == 3:
            img = Image.fromarray(data.transpose(1, 2, 0), mode="RGB")
        elif bands == 1:
            img = Image.fromarray(data[0], mode="L")
        else:
            img = Image.fromarray(data[:3].transpose(1, 2, 0), mode="RGB")

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except ImportError:
        log.debug("Pillow not available — cannot encode PNG thumbnail")
        return None


def thumbnail_url(scene_id: str, bbox: List[float]) -> str:
    """Build the API URL that serves a cached thumbnail."""
    key = cache_key(scene_id, bbox)
    return f"/api/thumbnails/{scene_id}?key={key}"


def get_cached_thumbnail(key: str) -> Optional[bytes]:
    """Retrieve a thumbnail from cache by its key."""
    return _cache.get(key)


def clear_cache() -> None:
    """Clear the thumbnail cache (useful in tests)."""
    _cache._store.clear()
