"""AOI (Area of Interest) Pydantic models for V2 API.

AOIs are first-class objects: every search, replay, and export is scoped to one.
Geometry is stored as GeoJSON (RFC 7946). PostGIS column type: GEOMETRY(Geometry, 4326).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class GeometryModel(BaseModel):
    """GeoJSON geometry — Polygon or MultiPolygon only (no client-side circles)."""
    type: str = Field(..., description="GeoJSON geometry type")
    coordinates: Any = Field(..., description="GeoJSON coordinate array")

    @field_validator("type")
    @classmethod
    def _allowed_types(cls, v: str) -> str:
        allowed = {"Polygon", "MultiPolygon"}
        if v not in allowed:
            raise ValueError(f"Geometry type must be one of {allowed}, got: {v!r}")
        return v


class AOIBase(BaseModel):
    """Fields shared by create / update requests."""
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable AOI label")
    geometry: GeometryModel = Field(..., description="GeoJSON Polygon or MultiPolygon (EPSG:4326)")
    description: Optional[str] = Field(default=None, max_length=2048)
    tags: List[str] = Field(default_factory=list, description="Free-form tags for filtering")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary analyst-owned metadata")


class AOICreate(AOIBase):
    """Request body for POST /api/v1/aois."""


class AOIUpdate(BaseModel):
    """Request body for PUT /api/v1/aois/:id — all fields optional."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    geometry: Optional[GeometryModel] = None
    description: Optional[str] = Field(default=None, max_length=2048)
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class AOIResponse(AOIBase):
    """Full AOI record returned by read endpoints."""
    id: str = Field(..., description="Stable AOI identifier (UUID)")
    created_at: datetime
    updated_at: datetime
    deleted: bool = Field(default=False)

    model_config = {"from_attributes": True}


class AOIListResponse(BaseModel):
    """Paginated list of AOIs."""
    items: List[AOIResponse]
    total: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    has_next: bool
