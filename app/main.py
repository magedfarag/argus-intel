from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import dependencies
from app.cache.client import CacheClient
from app.config import get_settings
from app.logging_config import configure_logging
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.rate_limiter import limiter, rate_limit_error_handler
from slowapi.errors import RateLimitExceeded

APP_DIR    = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    import logging as _log
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    registry = ProviderRegistry()
    registry.register(DemoProvider())
    if settings.sentinel2_is_configured():
        try:
            from app.providers.sentinel2 import Sentinel2Provider
            registry.register(Sentinel2Provider(settings))
        except Exception as exc:
            _log.getLogger(__name__).warning("Sentinel2Provider: %s", exc)
    if settings.landsat_is_configured():
        try:
            from app.providers.landsat import LandsatProvider
            registry.register(LandsatProvider(settings))
        except Exception as exc:
            _log.getLogger(__name__).warning("LandsatProvider: %s", exc)
    if settings.maxar_is_configured():
        try:
            from app.providers.maxar import MaxarProvider
            registry.register(MaxarProvider(settings))
        except Exception as exc:
            _log.getLogger(__name__).warning("MaxarProvider: %s", exc)
    if settings.planet_is_configured():
        try:
            from app.providers.planet import PlanetProvider
            registry.register(PlanetProvider(settings))
        except Exception as exc:
            _log.getLogger(__name__).warning("PlanetProvider: %s", exc)
    cache   = CacheClient.from_settings(settings)
    breaker = CircuitBreaker(
        failure_threshold=settings.circuit_breaker_failure_threshold,
        recovery_timeout=settings.circuit_breaker_recovery_timeout,
        redis_url=settings.redis_url,
    )
    # JobManager — created once; avoids per-request Redis connect/timeout
    jm = None
    if settings.redis_available() or settings.database_url:
        from app.services.job_manager import JobManager
        jm = JobManager(redis_url=settings.redis_url, database_url=settings.database_url)
    dependencies.set_registry(registry)
    dependencies.set_cache(cache)
    dependencies.set_breaker(breaker)
    dependencies.set_job_manager(jm)

    # ── V2 ConnectorRegistry (P1-3) ──────────────────────────────────────────
    from src.connectors.registry import ConnectorRegistry as V2Registry
    from src.connectors.earth_search import EarthSearchConnector
    from src.connectors.planetary_computer import PlanetaryComputerConnector
    v2_registry = V2Registry()
    v2_registry.register(EarthSearchConnector(stac_url=settings.earth_search_stac_url))
    v2_registry.register(PlanetaryComputerConnector(
        stac_url=settings.planetary_computer_stac_url,
        subscription_key=settings.planetary_computer_token,
    ))
    if settings.sentinel2_is_configured():
        from src.connectors.sentinel2 import CdseSentinel2Connector
        v2_registry.register(CdseSentinel2Connector(
            stac_url=settings.sentinel2_stac_url,
            token_url=settings.sentinel2_token_url,
            client_id=settings.sentinel2_client_id,
            client_secret=settings.sentinel2_client_secret,
        ))
    if settings.landsat_is_configured():
        from src.connectors.landsat import UsgsLandsatConnector
        v2_registry.register(UsgsLandsatConnector(stac_url=settings.landsat_stac_url))
    # P2-1: GDELT contextual events connector (public, no credentials required)
    from src.connectors.gdelt import GdeltConnector, DEFAULT_CONSTRUCTION_THEMES
    v2_registry.register(GdeltConnector(default_themes=DEFAULT_CONSTRUCTION_THEMES))
    # P3-1: AIS maritime connector (requires AISSTREAM_API_KEY)
    import os as _os
    aisstream_key = _os.getenv("AISSTREAM_API_KEY", "")
    if aisstream_key:
        try:
            from src.connectors.ais_stream import AisStreamConnector
            v2_registry.register(AisStreamConnector(api_key=aisstream_key))
        except Exception as exc:
            _log.getLogger(__name__).warning("AisStreamConnector: %s", exc)
    # P3-2: OpenSky aviation connector (optional credentials; always registered)
    try:
        from src.connectors.opensky import OpenSkyConnector
        v2_registry.register(OpenSkyConnector(
            username=_os.getenv("OPENSKY_USERNAME", ""),
            password=_os.getenv("OPENSKY_PASSWORD", ""),
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("OpenSkyConnector: %s", exc)
    from src.api.imagery import set_connector_registry, set_imagery_event_store
    set_connector_registry(v2_registry)

    # Shared EventStore for V2 event/playback/compare/analytics routers
    from src.services.event_store import EventStore as V2EventStore
    from src.api import events as _events_router_module
    from src.api.playback import set_event_store as _set_playback_store
    from src.api.analytics import set_analytics_event_store as _set_analytics_store
    _shared_store = _events_router_module._store  # reuse the module-level singleton
    set_imagery_event_store(_shared_store)
    _set_playback_store(_shared_store)
    _set_analytics_store(_shared_store)

    # PostGIS / SQLAlchemy engine (P0-4) — initialise when DATABASE_URL is set
    if settings.database_url:
        try:
            from src.storage.database import init_db
            init_db(settings.database_url)
        except Exception as exc:
            _log.getLogger(__name__).warning("Database init failed: %s", exc)

    _log.getLogger(__name__).info(
        "Application started | mode=%s providers=%s redis=%s",
        settings.app_mode,
        [p.provider_name for p in registry.all_providers()],
        "yes" if settings.redis_available() else "no",
    )
    yield

app = FastAPI(
    title="Construction Activity Monitor",
    version="2.0.0",
    description="Detects construction activity in satellite imagery.",
    lifespan=lifespan,
)

# Rate limiter — mount on app state so slowapi can access it
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)

# CORS Configuration: Restrict to configured origins; deny by default.
# Settings are lazily constructed at lifespan; we read them here for middleware.
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Only necessary methods
    allow_headers=["Content-Type", "Authorization"],  # Explicit header whitelist
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

from app.routers import analyze, config_router, credits, health, jobs, providers_router, search, thumbnails
from app.routers import ws_jobs
app.include_router(health.router)
app.include_router(config_router.router)
app.include_router(providers_router.router)
app.include_router(credits.router)
app.include_router(analyze.router)
app.include_router(jobs.router)
app.include_router(search.router)
app.include_router(ws_jobs.router)
app.include_router(thumbnails.router)

# ── V2 routes (P1-2, P1-3, P1-4, P1-5, P2-2, P2-3, P4-1, P4-2) ────────────
from src.api import aois as aois_router_module
from src.api import events as events_router_module
from src.api import exports as exports_router_module
from src.api import imagery as imagery_router_module
from src.api import playback as playback_router_module
from src.api import analytics as analytics_router_module
from src.api import source_health as source_health_router_module
app.include_router(aois_router_module.router)
app.include_router(events_router_module.router)
app.include_router(exports_router_module.router)
app.include_router(imagery_router_module.router)
app.include_router(playback_router_module.router)
app.include_router(analytics_router_module.router)
app.include_router(source_health_router_module.router)

# ── Prometheus metrics (P0-5.3) ──────────────────────────────────────────────
try:
    from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore[import]
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/healthz", "/readyz", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
except ImportError:
    pass  # prometheus-fastapi-instrumentator not installed; metrics endpoint disabled
