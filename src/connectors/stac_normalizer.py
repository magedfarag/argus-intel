"""Shared STAC → CanonicalEvent normalization utility.

P1-3.8: Converts raw STAC items from any catalog (CDSE, USGS, Element84,
Planetary Computer) into ``imagery_acquisition`` CanonicalEvent objects
ready for storage in the PostGIS canonical_events table.

All normalizers must be pure (no I/O) and raise NormalizationError for
records that cannot be safely transformed.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import NormalizationError
from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    ImageryAttributes,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)


def _parse_datetime(raw: Optional[str]) -> datetime:
    """Parse an ISO-8601 string into a UTC-aware datetime.

    Raises NormalizationError if the string is missing or unparseable.
    """
    if not raw:
        raise NormalizationError("STAC item is missing a datetime field")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise NormalizationError(f"Cannot parse datetime {raw!r}: {exc}") from exc


def _centroid_from_geometry(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a rough centroid from GeoJSON geometry (flat-earth approximation)."""
    geom_type = geometry.get("type", "")
    coords = geometry.get("coordinates", [])

    if geom_type == "Point":
        return {"type": "Point", "coordinates": coords}

    if geom_type == "Polygon" and coords:
        # Exterior ring centroid (mean of vertices)
        ring = coords[0]
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        return {"type": "Point", "coordinates": [
            sum(lons) / len(lons),
            sum(lats) / len(lats),
        ]}

    if geom_type == "MultiPolygon" and coords:
        # Centroid of first polygon ring
        ring = coords[0][0]
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        return {"type": "Point", "coordinates": [
            sum(lons) / len(lons),
            sum(lats) / len(lats),
        ]}

    # Fallback: bbox centre if geometry is null/unsupported
    raise NormalizationError(f"Unsupported geometry type for centroid: {geom_type!r}")


def _geometry_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return geometry from STAC item, falling back to bbox-derived polygon."""
    geometry = item.get("geometry")
    if geometry and geometry.get("type") and geometry.get("coordinates") is not None:
        return geometry

    bbox = item.get("bbox")
    if bbox and len(bbox) >= 4:
        w, s, e, n = bbox[:4]
        return {
            "type": "Polygon",
            "coordinates": [[
                [w, s], [e, s], [e, n], [w, n], [w, s],
            ]],
        }

    raise NormalizationError("STAC item has neither geometry nor bbox")


def _detect_platform(item: Dict[str, Any]) -> Optional[str]:
    """Extract platform/satellite name from STAC item properties."""
    props = item.get("properties", {})
    # STAC EO extension
    platform = props.get("platform") or props.get("constellation") or props.get("mission")
    if platform:
        return str(platform)
    # Landsat-specific
    satellite_id = props.get("landsat:satellite_id")
    if satellite_id:
        return satellite_id.replace("_", "-").title()
    return None


def _detect_gsd(item: Dict[str, Any]) -> Optional[float]:
    """Extract ground sample distance from STAC item."""
    props = item.get("properties", {})
    gsd = props.get("gsd")
    if gsd is not None:
        try:
            return float(gsd)
        except (ValueError, TypeError):
            pass
    # Per-band resolution fallback
    for asset in item.get("assets", {}).values():
        val = asset.get("gsd")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def _build_bands_list(item: Dict[str, Any]) -> List[str]:
    """Collect available spectral band keys from assets."""
    bands: List[str] = []
    for key in item.get("assets", {}):
        if key.upper().startswith("B") or key.lower() in {
            "red", "green", "blue", "nir", "nir08", "swir16", "swir22",
            "rededge", "coastal", "qa_pixel", "scl",
        }:
            bands.append(key)
    return bands


def stac_item_to_canonical_event(
    item: Dict[str, Any],
    connector_id: str,
    source: str,
    license_record: Optional[LicenseRecord] = None,
    raw_source_ref: str = "stac://unknown",
) -> CanonicalEvent:
    """Convert a raw STAC item dict into a CanonicalEvent.

    Args:
        item: Raw STAC item dict from the catalog API.
        connector_id: Connector module identifier (e.g. ``connector.cdse.stac``).
        source: Normalised provider code (e.g. ``copernicus-cdse``).
        license_record: Override the default LicenseRecord. If None, uses
            permissive defaults appropriate for free public catalogs.
        raw_source_ref: S3-style path or source URL for provenance tracking.

    Returns:
        A validated CanonicalEvent.

    Raises:
        NormalizationError: If required fields are missing or invalid.
    """
    props = item.get("properties", {})

    # ── Datetime ─────────────────────────────────────────────────────────────
    dt_str = props.get("datetime") or props.get("start_datetime")
    event_time = _parse_datetime(dt_str)

    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    if props.get("start_datetime") and props.get("end_datetime"):
        try:
            time_start = _parse_datetime(props["start_datetime"])
            time_end = _parse_datetime(props["end_datetime"])
        except NormalizationError:
            pass  # Non-fatal; event_time is still valid

    # ── Geometry ─────────────────────────────────────────────────────────────
    geometry = _geometry_from_item(item)
    centroid = _centroid_from_geometry(geometry)

    # ── Identity ──────────────────────────────────────────────────────────────
    entity_id = item.get("id") or item.get("stac_id")
    if not entity_id:
        raise NormalizationError("STAC item is missing an 'id' field")

    event_id = make_event_id(source, entity_id, event_time)

    # ── Imagery attributes ────────────────────────────────────────────────────
    cloud_cover = props.get("eo:cloud_cover")
    try:
        cloud_cover_pct = float(cloud_cover) if cloud_cover is not None else None
    except (ValueError, TypeError):
        cloud_cover_pct = None

    # Scene URL — prefer B08/NIR thumbnail, fall back to any visual asset
    assets = item.get("assets", {})
    scene_url = (
        assets.get("visual", {}).get("href")
        or assets.get("thumbnail", {}).get("href")
        or assets.get("overview", {}).get("href")
    )

    attrs = ImageryAttributes(
        platform=_detect_platform(item),
        sensor=props.get("instrument") or props.get("instruments"),
        gsd_m=_detect_gsd(item),
        cloud_cover_pct=cloud_cover_pct,
        off_nadir_angle=props.get("view:off_nadir") or props.get("off_nadir"),
        sun_azimuth=props.get("view:sun_azimuth"),
        scene_url=scene_url,
        bands_available=_build_bands_list(item),
        processing_level=props.get("processing:level") or props.get("product_type"),
    )

    return CanonicalEvent(
        event_id=event_id,
        source=source,
        source_type=SourceType.IMAGERY_CATALOG,
        entity_type=EntityType.IMAGERY_SCENE,
        entity_id=entity_id,
        event_type=EventType.IMAGERY_ACQUISITION,
        event_time=event_time,
        time_start=time_start,
        time_end=time_end,
        geometry=geometry,
        centroid=centroid,
        confidence=None,
        quality_flags=["cloud-filtered"] if cloud_cover_pct is not None and cloud_cover_pct > 20 else [],
        attributes=attrs.model_dump(exclude_none=True),
        normalization=NormalizationRecord(normalized_by=connector_id),
        provenance=ProvenanceRecord(
            raw_source_ref=raw_source_ref,
            source_record_id=entity_id,
            source_url=item.get("links", [{}])[0].get("href") if item.get("links") else None,
        ),
        license=license_record or LicenseRecord(
            access_tier="public",
            commercial_use="check-provider-terms",
            redistribution="check-provider-terms",
            attribution_required=True,
        ),
    )
