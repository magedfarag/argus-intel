"""Pydantic models for the imagery search API (P1-3.5 – P1-3.7).

Request and response shapes for:
  POST /api/v1/imagery/search
  GET  /api/v1/imagery/items/{item_id}
  GET  /api/v1/imagery/providers
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ImagerySearchRequest(BaseModel):
    """Parameters for a multi-catalog STAC imagery search."""

    geometry: Dict[str, Any] = Field(
        ...,
        description="GeoJSON Polygon or MultiPolygon of the AOI (EPSG:4326)",
    )
    start_time: datetime = Field(
        ...,
        description="Search window start (UTC-aware ISO 8601)",
    )
    end_time: datetime = Field(
        ...,
        description="Search window end (UTC-aware ISO 8601)",
    )
    cloud_threshold: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Maximum cloud cover percentage to accept",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum items to return per catalog",
    )
    connectors: Optional[List[str]] = Field(
        default=None,
        description=(
            "Limit search to specific connector IDs. "
            "If omitted, all enabled imagery connectors are queried."
        ),
    )

    @field_validator("geometry")
    @classmethod
    def _validate_geojson_type(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if v.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry.type must be 'Polygon' or 'MultiPolygon'")
        if "coordinates" not in v:
            raise ValueError("geometry must include 'coordinates'")
        return v

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _enforce_utc(cls, v: Any) -> Any:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError("Naive datetime rejected — provide UTC-aware datetime")
        return v


class ConnectorResultSummary(BaseModel):
    """Per-connector summary within a multi-catalog search response."""

    connector_id: str
    display_name: str
    item_count: int
    error: Optional[str] = None


class ImageryItemSummary(BaseModel):
    """Lightweight representation of a single STAC scene in search results."""

    event_id: str
    source: str
    entity_id: Optional[str]
    event_time: datetime
    geometry: Dict[str, Any]
    centroid: Dict[str, Any]
    cloud_cover_pct: Optional[float] = None
    platform: Optional[str] = None
    gsd_m: Optional[float] = None
    processing_level: Optional[str] = None
    scene_url: Optional[str] = None
    bands_available: List[str] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)
    license_access_tier: str = "public"
    connector_id: str


class ImagerySearchResponse(BaseModel):
    """Response from POST /api/v1/imagery/search."""

    total_items: int
    items: List[ImageryItemSummary]
    connector_summaries: List[ConnectorResultSummary]
    search_time_ms: Optional[float] = None


class ImageryProviderInfo(BaseModel):
    """Single provider entry returned by GET /api/v1/imagery/providers."""

    connector_id: str
    display_name: str
    source_type: str
    healthy: bool
    message: str
    requires_auth: bool = False
    collections: List[str] = Field(default_factory=list)


class ImageryProvidersResponse(BaseModel):
    """Response from GET /api/v1/imagery/providers."""

    providers: List[ImageryProviderInfo]
    total: int
