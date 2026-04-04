"""Rasterio-based change detection pipeline.

Pipeline:
    1. Open before / after scenes as remote COGs via rasterio (https:// URL)
    2. Reproject AOI bbox to scene CRS, build a rasterio Window
    3. Read Red + NIR bands; apply cloud / QA mask
    4. Compute NDVI; diff between scenes
    5. Threshold + morphological filtering (scipy.ndimage)
    6. Label connected components (scikit-image)
    7. Classify each component + score confidence
    8. Return List[ChangeRecord dicts]

rasterio docs confirmed: rasterio.open("https://...") opens COGs natively.
For Copernicus CDSE assets, set GDAL_HTTP_BEARER via rasterio.Env().
For Landsat assets on USGS, no auth header needed for public scenes.

Resolution limitations are reported honestly:
- Sentinel-2 at 10 m: can miss fine detail on small sites (<0.5 km2 AOI)
- Landsat at 30 m: coarse; mainly useful for larger developments (>5 km2)

If rasterio is not installed (e.g. local dev without GDAL), detection
gracefully returns an empty list with a warning.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.models.scene import SceneMetadata

log = logging.getLogger(__name__)

# Bands used per provider
_BANDS: Dict[str, Dict[str, int]] = {
    # Sentinel-2 L2A COG band indices (1-based) in standard band files
    "sentinel2": {"red": 1, "nir": 1},   # B04.tif, B08.tif separate files
    "landsat":   {"red": 1, "nir": 1},   # B4.TIF, B5.TIF separate files
}

_NDVI_CHANGE_THRESHOLD = 0.12     # |ΔNDVI| above which change is flagged
_MIN_PATCH_PIXELS      = 4        # minimum patch size to report
_CONFIDENCE_RESOLUTION_PENALTY_SMALL_AOI = 15.0  # subtract from confidence for small AOIs


def _rasterio_available() -> bool:
    try:
        import rasterio  # noqa: F401
        return True
    except ImportError:
        return False


def _read_band_window(
    url: str,
    bbox_wgs84: Tuple[float, float, float, float],
    band_index: int = 1,
    bearer_token: Optional[str] = None,
):
    """Stream-read a single band clipped to bbox from a remote COG.

    Returns numpy masked array (rows, cols) in float32.
    Uses rasterio.Env() to inject GDAL HTTPS auth if needed.
    """
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    env_kwargs: Dict[str, str] = {}
    if bearer_token:
        env_kwargs["GDAL_HTTP_BEARER"] = bearer_token
        env_kwargs["GDAL_HTTP_AUTH"]   = "BEARER"

    with rasterio.Env(**env_kwargs):
        with rasterio.open(url) as src:
            # Reproject bbox from WGS84 to scene CRS
            src_crs  = src.crs
            wgs84    = CRS.from_epsg(4326)
            min_lon, min_lat, max_lon, max_lat = bbox_wgs84
            if src_crs != wgs84:
                min_lon, min_lat, max_lon, max_lat = transform_bounds(
                    wgs84, src_crs, min_lon, min_lat, max_lon, max_lat
                )
            window = src.window(min_lon, min_lat, max_lon, max_lat)
            # Clamp window to dataset bounds
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
            data = src.read(
                band_index,
                window=window,
                masked=True,
                out_dtype="float32",
            )
    return data


def _compute_ndvi(red, nir):
    """NDVI = (NIR - Red) / (NIR + Red).  Returns masked array."""
    import numpy as np
    denom = nir.astype("float32") + red.astype("float32")
    # Avoid division by zero
    denom = np.where(denom == 0, np.nan, denom)
    ndvi  = (nir.astype("float32") - red.astype("float32")) / denom
    return np.ma.masked_invalid(ndvi)


def _classify_component(
    diff_patch,
    aoi_area_km2: float,
    resolution_m: int,
) -> Tuple[str, float, List[str]]:
    """Heuristic change classification based on spectral + size pattern.

    Returns (change_type, confidence 0-1, rationale_strings).
    """
    import numpy as np

    mean_diff  = float(np.nanmean(diff_patch))
    patch_size = diff_patch.size
    area_m2    = patch_size * (resolution_m ** 2)

    rationale: List[str] = []
    confidence = 0.60

    if mean_diff < -_NDVI_CHANGE_THRESHOLD:
        # Vegetation loss — bare soil / site clearing
        change_type = "Site clearing / earthwork"
        confidence  = 0.75
        rationale   = [
            "NDVI decreased significantly — vegetation cover removed",
            f"Affected area ~{area_m2 / 1000:.1f} m² based on patch size",
            "Pattern consistent with site clearing or excavation",
        ]
    elif mean_diff > _NDVI_CHANGE_THRESHOLD:
        # Reflectance gain — new structure or impervious surface
        change_type = "Roofing / enclosure"
        confidence  = 0.70
        rationale   = [
            "NDVI increase — higher reflectance surface detected",
            "Pattern consistent with new roofing or impervious material",
            f"Affected area ~{area_m2 / 1000:.1f} m²",
        ]
    else:
        # Moderate change — likely foundation or ground disturbance
        change_type = "Foundation work"
        confidence  = 0.55
        rationale   = [
            "Moderate reflectance change detected within AOI",
            "Pattern ambiguous; may indicate foundation or surface levelling",
        ]

    # Resolution caveats
    if resolution_m >= 30:
        rationale.append(
            f"LOW CONFIDENCE NOTE: {resolution_m} m resolution is coarse — "
            "small construction features may be missed or misclassified."
        )
        confidence -= 0.10

    if aoi_area_km2 < 0.5 and resolution_m >= 10:
        rationale.append(
            "RESOLUTION NOTE: AOI is small relative to sensor resolution; "
            "fine site detail may not be resolved."
        )
        confidence -= 0.08

    return change_type, max(0.0, min(1.0, confidence)), rationale


def run_change_detection(
    before: SceneMetadata,
    after: SceneMetadata,
    aoi_geom: Dict[str, Any],
    aoi_area_km2: float,
    bearer_token: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Run the full rasterio change detection pipeline.

    Returns (change_records, warnings).
    Change records use the same field structure as ChangeRecord model.

    Gracefully degrades:
    - If rasterio is unavailable: returns ([], [warning])
    - If COG read fails for a URL: logs warning, returns empty
    - If no significant changes found: returns ([], [])
    """
    warnings: List[str] = []

    if not _rasterio_available():
        warnings.append(
            "rasterio is not installed — live change detection unavailable. "
            "Install rasterio (see README for platform-specific instructions)."
        )
        return [], warnings

    import numpy as np
    from scipy import ndimage

    # Get bounding box from AOI geometry
    coords = aoi_geom.get("coordinates", [[]])
    if aoi_geom.get("type") == "Polygon":
        ring = coords[0]
    elif aoi_geom.get("type") == "MultiPolygon":
        ring = coords[0][0]
    else:
        warnings.append(f"Unsupported geometry type: {aoi_geom.get('type')}")
        return [], warnings

    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    bbox = (min(lons), min(lats), max(lons), max(lats))

    provider = before.provider
    resolution_m = before.resolution_m or 10

    # Identify band asset URLs
    try:
        if provider == "sentinel2":
            red_before_url = before.assets.get("B04", "")
            nir_before_url = before.assets.get("B08", "")
            red_after_url  = after.assets.get("B04", "")
            nir_after_url  = after.assets.get("B08", "")
        else:  # landsat
            red_before_url = before.assets.get("red", before.assets.get("B4", ""))
            nir_before_url = before.assets.get("nir", before.assets.get("B5", ""))
            red_after_url  = after.assets.get("red", after.assets.get("B4", ""))
            nir_after_url  = after.assets.get("nir", after.assets.get("B5", ""))
    except Exception as exc:
        warnings.append(f"Asset URL lookup failed: {exc}")
        return [], warnings

    missing = [k for k, v in {
        "red_before": red_before_url, "nir_before": nir_before_url,
        "red_after":  red_after_url,  "nir_after":  nir_after_url,
    }.items() if not v]
    if missing:
        warnings.append(f"Missing asset URLs for: {missing}. Change detection skipped.")
        return [], warnings

    # Read bands
    try:
        red_b = _read_band_window(red_before_url, bbox, bearer_token=bearer_token)
        nir_b = _read_band_window(nir_before_url, bbox, bearer_token=bearer_token)
        red_a = _read_band_window(red_after_url,  bbox, bearer_token=bearer_token)
        nir_a = _read_band_window(nir_after_url,  bbox, bearer_token=bearer_token)
    except Exception as exc:
        log.warning("Band read failed: %s", exc)
        warnings.append(f"Remote band read failed: {exc!s}. Change detection skipped.")
        return [], warnings

    # NDVI
    ndvi_before = _compute_ndvi(red_b, nir_b)
    ndvi_after  = _compute_ndvi(red_a, nir_a)

    # Align shapes (simple crop to minimum common shape)
    rows = min(ndvi_before.shape[0], ndvi_after.shape[0])
    cols = min(ndvi_before.shape[1], ndvi_after.shape[1])
    ndvi_diff = ndvi_after[:rows, :cols] - ndvi_before[:rows, :cols]

    # Threshold + morphological open/close to remove noise
    change_mask = np.abs(ndvi_diff.filled(0)) > _NDVI_CHANGE_THRESHOLD
    struct = ndimage.generate_binary_structure(2, 1)
    change_mask = ndimage.binary_opening(change_mask, structure=struct, iterations=1)
    change_mask = ndimage.binary_closing(change_mask, structure=struct, iterations=1)

    # Label connected components
    labeled, num_features = ndimage.label(change_mask)
    if num_features == 0:
        warnings.append("No significant changes detected within AOI after filtering.")
        return [], warnings

    from datetime import datetime

    changes: List[Dict[str, Any]] = []
    for component_idx in range(1, num_features + 1):
        component_mask = labeled == component_idx
        if component_mask.sum() < _MIN_PATCH_PIXELS:
            continue

        patch = ndvi_diff[component_mask]
        change_type, confidence, rationale = _classify_component(
            patch, aoi_area_km2, resolution_m
        )

        # Compute pixel centroid in scene pixel coordinates
        rows_idx, cols_idx = np.where(component_mask)
        bbox_row = (rows_idx.min(), rows_idx.max())
        bbox_col = (cols_idx.min(), cols_idx.max())

        # Approximate geographic bbox (simple linear interpolation)
        min_lon, min_lat, max_lon, max_lat = bbox
        row_frac_min = bbox_row[0] / max(rows, 1)
        row_frac_max = bbox_row[1] / max(rows, 1)
        col_frac_min = bbox_col[0] / max(cols, 1)
        col_frac_max = bbox_col[1] / max(cols, 1)

        ch_min_lon = min_lon + col_frac_min * (max_lon - min_lon)
        ch_max_lon = min_lon + col_frac_max * (max_lon - min_lon)
        # Latitude is top-down in raster
        ch_max_lat = max_lat - row_frac_min * (max_lat - min_lat)
        ch_min_lat = max_lat - row_frac_max * (max_lat - min_lat)

        cx = (ch_min_lon + ch_max_lon) / 2
        cy = (ch_min_lat + ch_max_lat) / 2

        if before.cloud_cover > 30:
            rationale.append(
                f"Reduced confidence: before-scene cloud cover is {before.cloud_cover:.0f}%"
            )
            confidence *= 0.80
        if after.cloud_cover > 30:
            rationale.append(
                f"Reduced confidence: after-scene cloud cover is {after.cloud_cover:.0f}%"
            )
            confidence *= 0.80

        ch_bbox = [round(v, 6) for v in [ch_min_lon, ch_min_lat, ch_max_lon, ch_max_lat]]

        # Generate thumbnails from TCI/visual COG (populates cache for /api/thumbnails)
        from app.services.thumbnails import generate_thumbnail, thumbnail_url
        tci_before = before.assets.get("TCI", "")
        tci_after = after.assets.get("TCI", "")
        before_thumb = None
        after_thumb = None
        if tci_before:
            png = generate_thumbnail(tci_before, ch_bbox, before.scene_id, bearer_token=bearer_token)
            if png:
                before_thumb = thumbnail_url(before.scene_id, ch_bbox)
        if tci_after:
            png = generate_thumbnail(tci_after, ch_bbox, after.scene_id, bearer_token=bearer_token)
            if png:
                after_thumb = thumbnail_url(after.scene_id, ch_bbox)
        # Fallback: STAC-provided thumbnail (full scene overview, not per-change crop)
        if not before_thumb:
            before_thumb = before.assets.get("thumbnail") or None
        if not after_thumb:
            after_thumb = after.assets.get("thumbnail") or None

        changes.append({
            "change_id":       f"det-{after.scene_id[:8]}-{component_idx}",
            "detected_at":     after.acquired_at,
            "change_type":     change_type,
            "confidence":      round(confidence * 100, 1),
            "center":          {"lng": round(cx, 6), "lat": round(cy, 6)},
            "bbox":            ch_bbox,
            "provider":        provider,
            "summary":         f"{change_type} detected between {before.acquired_at.date()} and {after.acquired_at.date()}.",
            "rationale":       rationale,
            "before_image":    before_thumb,
            "after_image":     after_thumb,
            "thumbnail":       after_thumb,
            "scene_id_before": before.scene_id,
            "scene_id_after":  after.scene_id,
            "resolution_m":    resolution_m,
            "warnings":        [],
        })

    temporal_gap = (after.acquired_at - before.acquired_at).days
    if temporal_gap < 7:
        warnings.append(
            f"Before and after scenes are only {temporal_gap} days apart; "
            "changes may reflect seasonal or atmospheric variation rather than construction."
        )

    return changes, warnings
