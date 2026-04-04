"""API response models."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChangeRecord(BaseModel):
    change_id: str
    detected_at: datetime
    change_type: str
    confidence: float = Field(ge=0.0, le=100.0)
    center: Dict[str, float]
    bbox: List[float]
    provider: str
    summary: str
    rationale: List[str]
    before_image: str
    after_image: str
    thumbnail: str
    # Live mode extras (omitted in demo mode)
    scene_id_before: Optional[str] = None
    scene_id_after: Optional[str] = None
    resolution_m: Optional[int] = None
    warnings: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    analysis_id: str
    requested_area_km2: float
    provider: str
    is_demo: bool = Field(
        default=False,
        description="True when results are synthetic demo data",
    )
    request_bounds: List[float]
    imagery_window: Dict[str, str]
    warnings: List[str]
    changes: List[ChangeRecord]
    stats: Dict[str, Any]


class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    result: Optional[AnalyzeResponse] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    available: bool
    reason: Optional[str] = None   # why unavailable, if applicable
    resolution_m: Optional[int] = None
    notes: List[str] = Field(default_factory=list)


class ProvidersResponse(BaseModel):
    providers: List[ProviderInfo]
    demo_available: bool


class HealthResponse(BaseModel):
    status: str
    mode: str
    demo_available: bool = True
    redis: str
    celery_worker: str
    providers: Dict[str, str]
    version: str = "2.0.0"
    circuit_breakers: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-provider circuit breaker state (closed/open/half_open)",
    )
    job_manager: str = Field(
        default="unknown",
        description="Job persistence backend in use (redis+postgresql / redis / memory)",
    )
    cache_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Cache hit/miss ratio and backend type",
    )
    database: str = Field(
        default="not_configured",
        description="PostgreSQL connectivity status",
    )
    object_storage: str = Field(
        default="not_configured",
        description="S3/MinIO connectivity status",
    )


class ConfigResponse(BaseModel):
    today: str
    min_area_km2: float
    max_area_km2: float
    max_lookback_days: int
    supported_providers: List[str]
    app_mode: str
    async_area_threshold_km2: float
    default_cloud_threshold: float
    cache_ttl_seconds: int
    redis_available: bool
    celery_available: bool


class SceneSearchResult(BaseModel):
    scene_id: str
    provider: str
    satellite: str
    acquired_at: str
    cloud_cover: float
    bbox: List[float]
    resolution_m: int
    asset_urls: Dict[str, str]


class SearchResponse(BaseModel):
    scenes: List[SceneSearchResult]
    total: int
    provider: str
    warnings: List[str]


class CreditsResponse(BaseModel):
    provider_request_counts: Dict[str, int]
    cache_hit_rate: float
    cache_hits: int
    cache_misses: int
    estimated_scenes_fetched: int
