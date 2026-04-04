"""API request models."""
from __future__ import annotations
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

_TODAY = date(2026, 3, 28)   # anchored for demo dataset; live path uses date.today()
_MAX_LOOKBACK = 30


class CoordinatesGeometry(BaseModel):
    type: str = Field(pattern="^(Polygon|MultiPolygon)$")
    coordinates: list


class AnalyzeRequest(BaseModel):
    geometry: CoordinatesGeometry
    start_date: date
    end_date: date
    provider: str = Field(
        default="auto",
        description="auto | demo | sentinel2 | landsat",
    )
    area_km2: Optional[float] = Field(
        default=None,
        description="Client-computed area; backend re-validates regardless",
    )
    cloud_threshold: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Maximum acceptable cloud cover percentage",
    )
    processing_mode: Literal["fast", "balanced", "thorough"] = Field(
        default="balanced",
    )
    async_execution: bool = Field(
        default=False,
        description="If True, return job_id immediately and process in background",
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "AnalyzeRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        return self


class SearchRequest(BaseModel):
    """Search imagery without running analysis."""
    geometry: CoordinatesGeometry
    start_date: date
    end_date: date
    provider: str = Field(default="auto")
    cloud_threshold: float = Field(default=20.0, ge=0.0, le=100.0)
    max_results: int = Field(default=10, ge=1, le=50)
