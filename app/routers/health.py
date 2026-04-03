"""Health check endpoints.

Exposes three endpoints (P0-5.1):
  GET /api/health   — legacy full status (retained for backward compat)
  GET /healthz      — liveness probe (is the process running?)
  GET /readyz       — readiness probe (is the service ready to serve traffic?)

/healthz always returns 200 if the process is alive.
/readyz returns 200 only when critical dependencies (cache, registry) are
operational; returns 503 otherwise so the orchestrator can hold traffic.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.cache.client import CacheClient
from app.config import AppSettings
from app.dependencies import get_app_settings, get_cache, get_registry
from app.models.responses import HealthResponse
from app.providers.registry import ProviderRegistry

router = APIRouter(tags=["system"])


@router.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Service and dependency health check",
)
def health(
    settings: Annotated[AppSettings,      Depends(get_app_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
    cache:    Annotated[CacheClient,      Depends(get_cache)],
) -> HealthResponse:
    provider_status = {}
    for p in registry.all_providers():
        ok, msg = registry.get_availability(p.provider_name)
        provider_status[p.provider_name] = "ok" if ok else msg

    # Celery status — probe via inspect (best-effort)
    celery_status = "not_configured"
    if settings.redis_available():
        try:
            from celery.app.control import Inspect
            from app.workers.celery_app import celery_app
            active = celery_app.control.inspect(timeout=1).active()
            celery_status = "ok" if active is not None else "no_workers"
        except Exception:  # noqa: BLE001
            celery_status = "unreachable"

    return HealthResponse(
        status="ok",
        mode=settings.app_mode,
        demo_available=registry.is_available("demo"),
        redis="ok" if cache.is_healthy() else "unavailable",
        celery_worker=celery_status,
        providers=provider_status,
    )


@router.get(
    "/healthz",
    summary="Liveness probe — returns 200 if the process is running",
    tags=["system"],
)
def liveness() -> dict:
    """Kubernetes/ECS liveness probe.

    Returns 200 unconditionally: if this endpoint responds, the process is alive.
    No dependency checks — those live in /readyz.
    """
    return {"status": "alive"}


@router.get(
    "/readyz",
    summary="Readiness probe — returns 200 only when service is ready to serve traffic",
    tags=["system"],
)
def readiness(
    cache: Annotated[CacheClient, Depends(get_cache)],
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
    settings: Annotated[AppSettings, Depends(get_app_settings)],
    response: Response,
) -> dict:
    """Kubernetes/ECS readiness probe (P0-5.5).

    Checks:
      - cache: in-memory or Redis layer initialised
      - providers: at least one provider registered
      - database: PostGIS reachable (skipped when DATABASE_URL not set)
      - object_storage: S3/MinIO reachable (skipped when not configured)

    Returns 200 when the service can serve traffic.
    Returns 503 when critical dependencies are not ready.
    """
    checks: dict = {
        "cache": cache.is_healthy(),
        "providers": len(registry.all_providers()) > 0,
    }

    # PostGIS check (P0-5.5)
    if settings.database_url:
        try:
            from src.storage.database import check_db_connectivity
            ok, _msg = check_db_connectivity()
            checks["database"] = ok
        except Exception:  # noqa: BLE001
            checks["database"] = False

    # Object storage check (P0-5.5) — best-effort ping
    if settings.object_storage_bucket:
        try:
            import boto3  # type: ignore[import]
            s3 = boto3.client(
                "s3",
                endpoint_url=settings.object_storage_endpoint or None,
                aws_access_key_id=settings.object_storage_access_key or None,
                aws_secret_access_key=settings.object_storage_secret_key or None,
            )
            s3.head_bucket(Bucket=settings.object_storage_bucket)
            checks["object_storage"] = True
        except Exception:  # noqa: BLE001
            checks["object_storage"] = False

    ready = all(checks.values())
    if not ready:
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}

