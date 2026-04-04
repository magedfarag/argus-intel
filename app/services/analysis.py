"""AnalysisService — orchestrates provider search, scene selection, and detection.

Provider resolution strategy (controlled by APP_MODE):
  DEMO:       always DemoProvider, is_demo=True
  STAGING:    requested → priority chain → DemoProvider fallback (is_demo=True)
  PRODUCTION: requested → priority chain → ProviderUnavailableError (fail-fast, no demo)
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from app.cache.client import CacheClient
from app.config import AppMode, AppSettings
from app.models.jobs import Job, JobState
from app.models.requests import AnalyzeRequest
from app.models.responses import AnalyzeResponse, ChangeRecord
from app.models.scene import SceneMetadata
from app.providers.base import ProviderUnavailableError, SatelliteProvider
from app.providers.demo import (
    DemoProvider,
    MAX_AREA_KM2,
    MIN_AREA_KM2,
    TODAY,
    _polygon_area_km2,
)
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from app.services.job_manager import JobManager
from app.services.scene_selection import rank_scenes, select_scene_pair

log = logging.getLogger(__name__)

_ASSETS_URL_PREFIX = "/static/assets"


def _flatten_coords(geometry: Dict[str, Any]) -> List[List[float]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        if not coords:
            raise ValueError("Polygon must include at least one ring")
        return coords[0]
    if gtype == "MultiPolygon":
        if not coords or not coords[0]:
            raise ValueError("MultiPolygon must include at least one polygon")
        return coords[0][0]
    raise ValueError(f"Unsupported geometry type: {gtype}")


def _bounds(coords: List[List[float]]) -> List[float]:
    lngs = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]
    return [min(lngs), min(lats), max(lngs), max(lats)]


def _aoi_hash(bounds: List[float]) -> str:
    key = ",".join(f"{v:.4f}" for v in bounds)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _cache_key(provider: str, bounds: List[float], start: str, end: str, cloud: float) -> str:
    return f"analysis:{provider}:{_aoi_hash(bounds)}:{start}:{end}:{cloud:.0f}"


class AnalysisService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: CacheClient,
        settings: AppSettings,
        job_manager: Optional[JobManager] = None,
        breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self._registry    = registry
        self._cache       = cache
        self._settings    = settings
        self._job_manager = job_manager
        self._breaker     = breaker
        self._demo        = DemoProvider()

    def run_sync(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """Execute analysis synchronously and return a complete response."""
        coords = _flatten_coords(request.geometry.model_dump())
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        computed_area = _polygon_area_km2(coords)

        area_km2 = request.area_km2 if request.area_km2 is not None else computed_area
        bounds   = _bounds(coords)
        warnings: List[str] = []

        # Check cache
        cache_key = _cache_key(
            request.provider, bounds,
            request.start_date.isoformat(), request.end_date.isoformat(),
            request.cloud_threshold,
        )
        cached = self._cache.get(cache_key)
        if cached:
            log.info("Cache hit for %s", cache_key)
            return AnalyzeResponse(**cached)

        # Decide which provider to use
        provider, is_demo, provider_warnings = self._resolve_provider(request.provider)
        warnings.extend(provider_warnings)

        # Run analysis
        if is_demo:
            changes_raw = self._demo.generate_changes(
                bounds, request.start_date, request.end_date
            )
            warnings.append(
                "DEMO MODE: Results are synthetic curated data, not real satellite detections."
            )
        else:
            changes_raw, detection_warnings = self._run_live_with_fallback(
                provider, request, bounds, area_km2
            )
            warnings.extend(detection_warnings)

        # Build ChangeRecord objects
        changes = [ChangeRecord(**c) for c in changes_raw]

        total     = len(changes)
        avg_conf  = round(sum(c.confidence for c in changes) / total, 1) if total else 0.0

        response = AnalyzeResponse(
            analysis_id=str(uuid.uuid4()),
            requested_area_km2=round(area_km2, 4),
            provider=provider.provider_name if provider else "demo",
            is_demo=is_demo,
            request_bounds=[round(v, 6) for v in bounds],
            imagery_window={
                "start_date": request.start_date.isoformat(),
                "end_date":   request.end_date.isoformat(),
            },
            warnings=warnings,
            changes=changes,
            stats={
                "total_changes":  total,
                "avg_confidence": avg_conf,
                "change_types":   sorted({c.change_type for c in changes}),
                "is_demo":        is_demo,
            },
        )

        # Cache successful result
        self._cache.set(cache_key, response.model_dump(mode="json"))
        return response

    def submit_async(self, request: AnalyzeRequest) -> str:
        """Submit analysis to Celery worker; return job_id."""
        if not self._settings.effective_celery_broker():
            raise RuntimeError(
                "Celery broker is not configured. "
                "Set REDIS_URL (or CELERY_BROKER_URL) to enable async jobs."
            )
        try:
            from app.workers.tasks import run_analysis_task
            from app.models.jobs import JobState
        except ImportError as exc:
            raise RuntimeError(f"Celery workers not available: {exc}") from exc

        job: Optional[Job] = None
        if self._job_manager:
            job = self._job_manager.create_job(request.model_dump(mode="json"))

        task = run_analysis_task.delay(request.model_dump(mode="json"))

        # If job_manager is available, record Celery task id as job_id
        if job and self._job_manager:
            # Override job_id to match Celery task id for easy status lookup
            job.job_id = task.id
            self._job_manager._save(job)
            return job.job_id

        return task.id

    # ── Internal helpers ──────────────────────────────────────────────────

    def _resolve_provider(
        self, requested: str
    ):
        """Return (provider_instance, is_demo, warnings).

        Uses select_provider_by_mode() to determine the provider priority
        chain for the current app mode, then resolves accordingly.
        """
        mode = self._settings.app_mode
        priority, _desc = self._registry.select_provider_by_mode(mode)

        if mode == AppMode.DEMO or requested == "demo":
            return self._demo, True, []

        # Try requested provider first, then fall through priority chain
        provider = self._registry.select_provider(requested, mode=mode)
        if provider and provider.provider_name != "demo":
            return provider, False, []

        # Try remaining providers in mode-defined priority order
        for name in priority:
            if name == "demo":
                continue
            alt = self._registry.select_provider(name, mode=mode)
            if alt and alt.provider_name != "demo":
                return alt, False, [
                    f"Requested provider '{requested}' unavailable; "
                    f"using '{name}' from {mode.value} priority chain."
                ]

        # No live provider available — warn and fall back to demo
        msg = (
            f"Requested provider '{requested}' is not available "
            "(missing credentials or provider unreachable). "
            "Falling back to demo mode."
        )
        if mode == AppMode.PRODUCTION:
            raise ProviderUnavailableError(msg)
        return self._demo, True, [msg]

    def _run_live_with_fallback(
        self,
        primary: SatelliteProvider,
        request: AnalyzeRequest,
        bounds: List[float],
        area_km2: float,
    ):
        """Try primary provider, then alternates from the priority chain.

        In production mode, raises ProviderUnavailableError if all fail.
        In staging mode, falls back to demo data.
        """
        mode = self._settings.app_mode
        priority, _ = self._registry.select_provider_by_mode(mode)
        tried: set[str] = set()

        # Build ordered list: primary first, then remaining by priority
        providers_to_try: List[SatelliteProvider] = [primary]
        tried.add(primary.provider_name)
        for name in priority:
            if name in tried or name == "demo":
                continue
            alt = self._registry.select_provider(name)
            if alt and alt.provider_name != "demo":
                providers_to_try.append(alt)
                tried.add(name)

        last_exc: Optional[Exception] = None
        for provider in providers_to_try:
            try:
                changes_raw, detection_warnings = self._run_live_analysis(
                    provider, request, bounds, area_km2
                )
                if provider is not primary:
                    detection_warnings.append(
                        f"Primary provider '{primary.provider_name}' failed; "
                        f"fell back to '{provider.provider_name}'."
                    )
                return changes_raw, detection_warnings
            except ProviderUnavailableError as exc:
                log.warning(
                    "Provider %s failed: %s — trying next",
                    provider.provider_name, exc,
                )
                last_exc = exc

        # All live providers exhausted
        if mode == AppMode.PRODUCTION:
            raise ProviderUnavailableError(
                f"All live providers failed. Last error: {last_exc}"
            )
        # Staging: fall back to demo
        changes_raw = self._demo.generate_changes(
            bounds, request.start_date, request.end_date
        )
        return changes_raw, [
            f"All live providers failed (last: {last_exc}). "
            "Falling back to demo data.",
            "DEMO MODE: Results are synthetic curated data, not real satellite detections.",
        ]

    def _run_live_analysis(
        self,
        provider: SatelliteProvider,
        request: AnalyzeRequest,
        bounds: List[float],
        area_km2: float,
    ):
        """Search, rank, detect; return (changes_raw, warnings)."""
        from app.services.change_detection import run_change_detection

        warnings: List[str] = []
        pname = provider.provider_name

        # Circuit breaker check
        if self._breaker and self._breaker.is_open(pname):
            raise ProviderUnavailableError(
                f"Circuit breaker OPEN for {pname} — too many recent failures."
            )

        # Search scenes — record circuit breaker outcome
        try:
            scenes = provider.search_imagery(
                geometry=request.geometry.model_dump(),
                start_date=request.start_date.isoformat(),
                end_date=request.end_date.isoformat(),
                cloud_threshold=request.cloud_threshold,
                max_results=10,
            )
            if self._breaker:
                self._breaker.record_success(pname)
        except Exception as exc:
            if self._breaker:
                self._breaker.record_failure(pname)
            raise ProviderUnavailableError(f"Provider search failed: {exc}") from exc

        if not scenes:
            warnings.append(
                "No scenes found for the requested AOI and date range. "
                "Try expanding the date range or increasing cloud threshold."
            )
            return [], warnings

        ranked           = rank_scenes(scenes)
        before, after    = select_scene_pair(ranked)

        if before is None or after is None:
            warnings.append("Insufficient scenes for change detection (need at least 2).")
            return [], warnings

        # Run change detection
        changes, det_warnings = run_change_detection(
            before=before,
            after=after,
            aoi_geom=request.geometry.model_dump(),
            aoi_area_km2=area_km2,
        )
        warnings.extend(det_warnings)

        if provider.resolution_m and provider.resolution_m >= 30:
            warnings.append(
                f"Provider resolution is {provider.resolution_m} m — "
                "small construction site features may not be detectable."
            )

        return changes, warnings
