"""Celery tasks for async analysis execution."""
from __future__ import annotations

import logging
from typing import Any, Dict

from backend.app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(bind=True, name="run_analysis_task")
def run_analysis_task(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a full analysis and return the serialised AnalyzeResponse."""
        from backend.app.config import get_settings
        from backend.app.cache.client import CacheClient
        from backend.app.providers.demo import DemoProvider
        from backend.app.providers.registry import ProviderRegistry
        from backend.app.models.requests import AnalyzeRequest
        from backend.app.services.analysis import AnalysisService

        settings = get_settings()
        cache    = CacheClient.from_settings(settings)

        # Build minimal registry for worker process
        registry = ProviderRegistry()
        registry.register(DemoProvider())

        # Register live providers if configured
        if settings.sentinel2_is_configured():
            try:
                from backend.app.providers.sentinel2 import Sentinel2Provider
                registry.register(Sentinel2Provider(settings))
            except Exception as exc:
                log.warning("Sentinel2Provider unavailable in worker: %s", exc)

        if settings.landsat_is_configured():
            try:
                from backend.app.providers.landsat import LandsatProvider
                registry.register(LandsatProvider(settings))
            except Exception as exc:
                log.warning("LandsatProvider unavailable in worker: %s", exc)

        svc     = AnalysisService(registry=registry, cache=cache, settings=settings)
        request = AnalyzeRequest(**request_json)
        result  = svc.run_sync(request)
        return result.model_dump(mode="json")
