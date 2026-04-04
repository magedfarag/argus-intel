"""Imagery search router — POST /api/v1/imagery/search and companions.

P1-3.5 to P1-3.7: Multi-catalog STAC imagery search across all registered
V2 imagery connectors.  Results are normalized to CanonicalEvent and
returned as lightweight ImageryItemSummary objects.

P2-3.1: POST /api/v1/imagery/compare — before/after scene metadata comparison.

Endpoints:
  POST /api/v1/imagery/search          — multi-catalog search (P1-3.5)
  GET  /api/v1/imagery/items/{item_id} — single item detail (P1-3.6)
  GET  /api/v1/imagery/providers       — list enabled providers (P1-3.7)
  POST /api/v1/imagery/compare         — before/after pair comparison (P2-3.1)
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status

from src.connectors.base import ConnectorUnavailableError
from src.connectors.registry import ConnectorRegistry
from src.models.canonical_event import ImageryAttributes
from src.models.compare import (
    ImageryCompareRequest,
    ImageryCompareResponse,
    ImageryQualityAssessment,
)
from src.models.imagery import (
    ConnectorResultSummary,
    ImageryItemSummary,
    ImageryProviderInfo,
    ImageryProvidersResponse,
    ImagerySearchRequest,
    ImagerySearchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/imagery", tags=["imagery"])

# ── Module-level connector registry (lazily populated) ────────────────────────
# The registry is populated by the application lifespan and injected by calling
# ``set_connector_registry()`` from main.py, enabling test overrides without
# FastAPI dependency injection complexity.

_connector_registry: Optional[ConnectorRegistry] = None

# ── Module-level event store for compare endpoint (P2-3) ─────────────────────
# Shared with events router; populated by set_imagery_event_store() in lifespan.
_imagery_event_store: Optional[Any] = None


def set_connector_registry(registry: ConnectorRegistry) -> None:
    """Inject the module-level ConnectorRegistry. Called from app lifespan."""
    global _connector_registry
    _connector_registry = registry


def set_imagery_event_store(store: Any) -> None:
    """Inject the shared EventStore for the compare endpoint. Called from app lifespan."""
    global _imagery_event_store
    _imagery_event_store = store


def get_connector_registry() -> ConnectorRegistry:
    if _connector_registry is None:
        # Return an empty registry so the router degrades gracefully
        return ConnectorRegistry()
    return _connector_registry


# ── Helper ─────────────────────────────────────────────────────────────────────

def _canonical_to_summary(event: Any, connector_id: str) -> ImageryItemSummary:
    """Map a CanonicalEvent to a lightweight ImageryItemSummary."""
    attrs = event.attributes or {}
    return ImageryItemSummary(
        event_id=event.event_id,
        source=event.source,
        entity_id=event.entity_id,
        event_time=event.event_time,
        geometry=event.geometry,
        centroid=event.centroid,
        cloud_cover_pct=attrs.get("cloud_cover_pct"),
        platform=attrs.get("platform"),
        gsd_m=attrs.get("gsd_m"),
        processing_level=attrs.get("processing_level"),
        scene_url=attrs.get("scene_url"),
        bands_available=attrs.get("bands_available", []),
        quality_flags=event.quality_flags,
        license_access_tier=event.license.access_tier,
        connector_id=connector_id,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/search",
    response_model=ImagerySearchResponse,
    summary="Search imagery across all STAC catalogs",
    description=(
        "Query all enabled imagery connectors (CDSE Sentinel-2, USGS Landsat, "
        "Earth Search, Planetary Computer) for scenes intersecting the AOI and "
        "time window. Results are normalized to canonical events and sorted "
        "by acquisition time descending."
    ),
)
def search_imagery(request: ImagerySearchRequest) -> ImagerySearchResponse:
    registry = get_connector_registry()
    connectors = registry.connectors_by_source_type("imagery_catalog")

    if request.connectors:
        requested_ids = set(request.connectors)
        connectors = [c for c in connectors if c.connector_id in requested_ids]

    if not connectors:
        # Graceful empty response when no imagery connectors are registered
        return ImagerySearchResponse(
            total_items=0,
            items=[],
            connector_summaries=[],
        )

    all_items: List[ImageryItemSummary] = []
    summaries: List[ConnectorResultSummary] = []
    t_start = time.perf_counter()

    for connector in connectors:
        try:
            raw_items, warnings = connector.fetch_and_normalize(
                geometry=request.geometry,
                start_time=request.start_time,
                end_time=request.end_time,
                cloud_threshold=request.cloud_threshold,
                max_results=request.max_results,
            )
            for event in raw_items:
                all_items.append(_canonical_to_summary(event, connector.connector_id))
            summaries.append(ConnectorResultSummary(
                connector_id=connector.connector_id,
                display_name=connector.display_name,
                item_count=len(raw_items),
            ))
            if warnings:
                logger.warning(
                    "[%s] %d normalization warnings during search",
                    connector.connector_id,
                    len(warnings),
                )
        except ConnectorUnavailableError as exc:
            logger.warning("[%s] connector unavailable: %s", connector.connector_id, exc)
            summaries.append(ConnectorResultSummary(
                connector_id=connector.connector_id,
                display_name=connector.display_name,
                item_count=0,
                error=str(exc),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] unexpected error during search: %s", connector.connector_id, exc, exc_info=True)
            summaries.append(ConnectorResultSummary(
                connector_id=connector.connector_id,
                display_name=connector.display_name,
                item_count=0,
                error=f"Internal error: {type(exc).__name__}",
            ))

    # Sort merged results by event_time descending
    all_items.sort(key=lambda x: x.event_time, reverse=True)

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    return ImagerySearchResponse(
        total_items=len(all_items),
        items=all_items,
        connector_summaries=summaries,
        search_time_ms=round(elapsed_ms, 1),
    )


@router.get(
    "/items/{item_id}",
    response_model=ImageryItemSummary,
    summary="Get a single imagery item by its canonical event_id",
    description=(
        "Look up a previously returned imagery item by its canonical event_id. "
        "Fetches the item from the originating connector by reconstructing "
        "the source item_id from the event_id."
    ),
)
def get_imagery_item(item_id: str) -> ImageryItemSummary:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Single-item retrieval requires per-connector item fetch — "
            "store canonical events in PostGIS (P0-4) and query by event_id."
        ),
    )


@router.get(
    "/providers",
    response_model=ImageryProvidersResponse,
    summary="List all registered imagery providers",
    description=(
        "Returns health and capability information for every imagery connector "
        "registered with the V2 ConnectorRegistry."
    ),
)
def list_imagery_providers() -> ImageryProvidersResponse:
    registry = get_connector_registry()
    connectors = registry.connectors_by_source_type("imagery_catalog")

    providers: List[ImageryProviderInfo] = []
    for connector in connectors:
        health = connector.health()
        # Introspect connector for collections if attribute exists
        collections = getattr(connector, "_collections", [])
        requires_auth = bool(getattr(connector, "_needs_auth", False))
        providers.append(ImageryProviderInfo(
            connector_id=connector.connector_id,
            display_name=connector.display_name,
            source_type=connector.source_type,
            healthy=health.healthy,
            message=health.message,
            requires_auth=requires_auth,
            collections=list(collections),
        ))

    return ImageryProvidersResponse(providers=providers, total=len(providers))


# ── P2-3.1: Imagery Compare Endpoint ─────────────────────────────────────────


@router.post(
    "/compare",
    response_model=ImageryCompareResponse,
    summary="Compare two imagery scenes (before/after) side by side",
    description=(
        "Given two canonical event_ids (before and after scenes), returns a "
        "structured comparison including temporal gap, cloud cover deltas, and "
        "an overall pair quality rating. Both scenes must exist in the event store."
    ),
)
def compare_imagery(req: ImageryCompareRequest) -> ImageryCompareResponse:
    """Retrieve two imagery events by ID and compute a side-by-side comparison."""
    store = _imagery_event_store
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event store not available.",
        )

    before_event = store.get(req.before_event_id)
    after_event = store.get(req.after_event_id)

    if before_event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Before scene event_id '{req.before_event_id}' not found.",
        )
    if after_event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"After scene event_id '{req.after_event_id}' not found.",
        )

    # Ensure correct temporal ordering: before must be older than after
    if before_event.event_time >= after_event.event_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "before_event_id must have an earlier event_time than after_event_id. "
                f"Got before={before_event.event_time.isoformat()} "
                f"after={after_event.event_time.isoformat()}."
            ),
        )

    before_summary = _canonical_to_summary(before_event, before_event.source)
    after_summary = _canonical_to_summary(after_event, after_event.source)

    temporal_gap_days = (
        after_event.event_time - before_event.event_time
    ).total_seconds() / 86400.0

    cloud_before = before_summary.cloud_cover_pct
    cloud_after = after_summary.cloud_cover_pct

    # Quality rating heuristic
    notes: List[str] = []
    if temporal_gap_days < 7:
        notes.append("Temporal gap <7 days: change detection may be unreliable.")
    if cloud_before is not None and cloud_before > 20:
        notes.append(f"Before scene cloud cover {cloud_before:.0f}% exceeds 20% threshold.")
    if cloud_after is not None and cloud_after > 20:
        notes.append(f"After scene cloud cover {cloud_after:.0f}% exceeds 20% threshold.")
    if before_event.source != after_event.source:
        notes.append(
            f"Cross-sensor comparison: before={before_event.source}, "
            f"after={after_event.source}. Radiometric consistency not guaranteed."
        )

    cloud_ok = (cloud_before is None or cloud_before <= 20) and (
        cloud_after is None or cloud_after <= 20
    )
    if temporal_gap_days >= 7 and cloud_ok:
        rating = "good"
    elif temporal_gap_days >= 3 and (cloud_before or 0) <= 40 and (cloud_after or 0) <= 40:
        rating = "acceptable"
    else:
        rating = "poor"

    # Deterministic comparison_id
    comparison_id = hashlib.sha256(
        f"{req.before_event_id}:{req.after_event_id}".encode()
    ).hexdigest()[:16]

    return ImageryCompareResponse(
        comparison_id=comparison_id,
        before_scene=before_summary,
        after_scene=after_summary,
        quality=ImageryQualityAssessment(
            rating=rating,
            temporal_gap_days=round(temporal_gap_days, 2),
            cloud_cover_before=cloud_before,
            cloud_cover_after=cloud_after,
            notes=notes,
        ),
    )
