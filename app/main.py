from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app import dependencies
from app.audit_log import AuditLoggingMiddleware, configure_audit_logger
from app.cache.client import CacheClient
from app.config import get_settings
from app.logging_config import configure_logging
from app.performance_budgets import PerformanceBudgetMiddleware
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.rate_limiter import limiter, rate_limit_error_handler


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    import logging as _log
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    configure_audit_logger()
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
    from src.connectors.earth_search import EarthSearchConnector
    from src.connectors.planetary_computer import PlanetaryComputerConnector
    from src.connectors.registry import ConnectorRegistry as V2Registry
    v2_registry = V2Registry()
    v2_registry.register(EarthSearchConnector(stac_url=settings.earth_search_stac_url))
    v2_registry.register(PlanetaryComputerConnector(
        stac_url=settings.planetary_computer_stac_url,
        subscription_key=settings.planetary_computer_token,
    ))
    if settings.sentinel2_is_configured():
        from src.connectors.sentinel2 import _STAC_URL as _CDSE_STAC_URL
        from src.connectors.sentinel2 import _TOKEN_URL as _CDSE_TOKEN_URL
        from src.connectors.sentinel2 import CdseSentinel2Connector
        v2_registry.register(CdseSentinel2Connector(
            # Always use the CDSE STAC endpoint — not the V1 provider's Element84 URL.
            stac_url=_CDSE_STAC_URL,
            token_url=_CDSE_TOKEN_URL,
            client_id=settings.sentinel2_client_id,
            client_secret=settings.sentinel2_client_secret,
        ))
    if settings.landsat_is_configured():
        from src.connectors.landsat import UsgsLandsatConnector
        v2_registry.register(UsgsLandsatConnector(stac_url=settings.landsat_stac_url))
    # P2-1: GDELT contextual events connector (public, no credentials required)
    from src.connectors.gdelt import DEFAULT_CONSTRUCTION_THEMES, GdeltConnector
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
    # Free data sources — no credentials required ────────────────────────────
    # USGS Earthquake Catalog (public domain, zero auth)
    try:
        from src.connectors.usgs_earthquake import UsgsEarthquakeConnector
        v2_registry.register(UsgsEarthquakeConnector(
            api_url=settings.usgs_earthquake_api_url,
            min_magnitude=settings.usgs_earthquake_min_magnitude,
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("UsgsEarthquakeConnector: %s", exc)
    # NASA EONET Natural Events (CC0 / public domain, zero auth)
    try:
        from src.connectors.nasa_eonet import NasaEonetConnector
        v2_registry.register(NasaEonetConnector(
            api_url=settings.nasa_eonet_api_url,
            days_lookback=settings.nasa_eonet_days_lookback,
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("NasaEonetConnector: %s", exc)
    # Open-Meteo Weather Forecast (CC BY 4.0, zero auth)
    try:
        from src.connectors.open_meteo import OpenMeteoConnector
        v2_registry.register(OpenMeteoConnector(
            api_url=settings.open_meteo_api_url,
            forecast_hours=settings.open_meteo_forecast_hours,
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("OpenMeteoConnector: %s", exc)
    # Military / Gulf-specific data sources ─────────────────────────────────
    # ACLED Armed Conflict Location & Event Data (free API key + email required)
    if settings.acled_is_configured():
        try:
            from src.connectors.acled import AcledConnector
            v2_registry.register(AcledConnector(
                api_key=settings.acled_api_key,
                email=settings.acled_email,
                api_url=settings.acled_api_url,
            ))
        except Exception as exc:
            _log.getLogger(__name__).warning("AcledConnector: %s", exc)
    # NGA MSI Maritime Safety Information (zero auth, US Gov public domain)
    try:
        from src.connectors.nga_msi import NgaMsiConnector
        v2_registry.register(NgaMsiConnector(
            api_url=settings.nga_msi_api_url,
            default_nav_areas=[
                a.strip()
                for a in settings.nga_msi_default_nav_areas.split(",")
                if a.strip()
            ],
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("NgaMsiConnector: %s", exc)
    # OSM Overpass Military Features (zero auth, ODbL)
    try:
        from src.connectors.osm_military import OsmMilitaryConnector
        v2_registry.register(OsmMilitaryConnector(
            overpass_url=settings.osm_overpass_url,
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("OsmMilitaryConnector: %s", exc)
    # Environmental / signals intelligence sources ──────────────────────
    # NASA FIRMS Active Fire / Thermal Anomaly (DEMO_KEY works out of the box)
    try:
        from src.connectors.nasa_firms import NasaFirmsConnector
        v2_registry.register(NasaFirmsConnector(
            map_key=settings.nasa_firms_map_key,
            api_url=settings.nasa_firms_api_url,
            source=settings.nasa_firms_source,
            days_lookback=settings.nasa_firms_days_lookback,
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("NasaFirmsConnector: %s", exc)
    # NOAA Space Weather Prediction Center (zero auth)
    try:
        from src.connectors.noaa_swpc import NoaaSwpcConnector
        v2_registry.register(NoaaSwpcConnector(api_url=settings.noaa_swpc_api_url))
    except Exception as exc:
        _log.getLogger(__name__).warning("NoaaSwpcConnector: %s", exc)
    # OpenAQ Air Quality Network (zero auth)
    try:
        from src.connectors.openaq import OpenAqConnector
        v2_registry.register(OpenAqConnector(
            api_url=settings.openaq_api_url,
            api_key=settings.openaq_api_key,
        ))
    except Exception as exc:
        _log.getLogger(__name__).warning("OpenAqConnector: %s", exc)
    from src.api.imagery import set_connector_registry, set_imagery_event_store
    set_connector_registry(v2_registry)

    # Pre-register all V2 connectors into the health service so the health
    # dashboard shows every connector immediately — not only after first poll.
    from src.api.source_health import get_api_health_service as _get_health_svc
    _health_svc = _get_health_svc()
    for _conn in v2_registry.all_connectors(include_disabled=True):
        _cid = _conn.connector_id
        _disabled = _cid not in [c.connector_id for c in v2_registry.all_connectors()]
        if _disabled:
            _health_svc.record_error(_cid, "Connector disabled at startup", _conn.display_name, _conn.source_type)
        else:
            _health_svc._get_or_create(_cid, _conn.display_name, _conn.source_type)

    # Shared EventStore for V2 event/playback/compare/analytics routers
    from src.api import events as _events_router_module
    from src.api.analytics import set_analytics_event_store as _set_analytics_store
    from src.api.playback import set_event_store as _set_playback_store
    _shared_store = _events_router_module._store  # reuse the module-level singleton
    set_imagery_event_store(_shared_store)
    _set_playback_store(_shared_store)
    _set_analytics_store(_shared_store)

    # Seed the in-memory stores with synthetic demo data so the UI has
    # ship tracks, flight tracks, GDELT context, imagery, and an AOI on first load.
    try:
        from src.api.aois import _store as _aoi_store
        from src.services.demo_seeder import seed_aoi_store as _seed_aoi
        from src.services.demo_seeder import seed_event_store as _seed
        # Defensive reset: lifespan can run multiple times in the same process
        # (dev reload / test harness). Always reseed from a clean in-memory state
        # so stale AOI IDs and legacy telemetry cannot leak into playback.
        _aoi_store.clear()
        _shared_store.clear()
        _demo_aoi_id = _seed_aoi(_aoi_store)
        _seed_count = _seed(_shared_store, aoi_id=_demo_aoi_id)
        _log.getLogger(__name__).info("Demo seeder: AOI %s + %d events ingested", _demo_aoi_id, _seed_count)
    except Exception as _seed_exc:
        _log.getLogger(__name__).warning("Demo seeder failed: %s", _seed_exc)

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

    # ── In-process health prober (runs inside the FastAPI event loop) ────────
    # SourceHealthService is in-memory, so only probes from this process are
    # visible to the health dashboard.  Celery tasks update their own copy.
    import asyncio

    async def _periodic_health_probe() -> None:
        """Probe STAC catalogs + GDELT + OpenSky every 5 minutes."""
        import httpx

        _probe_log = _log.getLogger("health_prober")
        targets = {
            "earth-search": "https://earth-search.aws.element84.com/v1/",
            "planetary-computer": "https://planetarycomputer.microsoft.com/api/stac/v1/",
            "cdse-sentinel2": "https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a",
            "usgs-landsat": "https://landsatlook.usgs.gov/stac-server/",
            "gdelt-doc": "https://api.gdeltproject.org/api/v2/doc/doc?query=test&mode=artlist&maxrecords=1&format=json",
            "opensky": "https://opensky-network.org/api/states/all?lamin=0&lamax=1&lomin=0&lomax=1",
            "ais-stream": "https://aisstream.io/",  # basic liveness probe
            "usgs-earthquake": "https://earthquake.usgs.gov/fdsnws/event/1/version",
            "nasa-eonet": "https://eonet.gsfc.nasa.gov/api/v3/events?limit=1&status=open",
            "open-meteo": "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=0.1&hourly=cloud_cover&forecast_days=1",
            "nga-msi": "https://msi.nga.mil/api/publications/broadcast-warn?output=json&includePublications=true&status=active&navArea=IX",
            "osm-military": "https://overpass-api.de/api/status",
            "nasa-firms": "https://firms.modaps.eosdis.nasa.gov/api/area/json/DEMO_KEY/VIIRS_SNPP_NRT/0,0,0.001,0.001/1",
            "noaa-swpc": "https://services.swpc.noaa.gov/products/alerts.json",
            "openaq": "https://api.openaq.org/v3/locations?limit=1",
        }
        _source_types: dict[str, str] = {
            "earth-search": "imagery_catalog",
            "planetary-computer": "imagery_catalog",
            "cdse-sentinel2": "imagery_catalog",
            "usgs-landsat": "imagery_catalog",
            "gdelt-doc": "context_feed",
            "opensky": "telemetry",
            "ais-stream": "telemetry",
            "usgs-earthquake": "public_record",
            "nasa-eonet": "context_feed",
            "open-meteo": "context_feed",
            "nga-msi": "public_record",
            "osm-military": "public_record",
            "nasa-firms": "public_record",
            "noaa-swpc": "public_record",
            "openaq": "public_record",
        }
        while True:
            _probe_log.info("Running health probes for %d connectors", len(targets))
            async with httpx.AsyncClient(timeout=15.0) as client:
                for cid, url in targets.items():
                    stype = _source_types.get(cid, "unknown")
                    try:
                        resp = await client.get(url)
                        # Any HTTP response (even 4xx/5xx) means the service is
                        # reachable.  Only count connection/timeout failures as
                        # errors — e.g. GDELT returns 429 when rate-limited but
                        # the service is alive.
                        if resp.status_code < 500:
                            _health_svc.record_success(cid, source_type=stype)
                            _probe_log.debug("probe %s: ok (%d)", cid, resp.status_code)
                        else:
                            _health_svc.record_error(cid, f"HTTP {resp.status_code}", source_type=stype)
                            _probe_log.warning("probe %s: HTTP %d", cid, resp.status_code)
                    except Exception as exc:  # noqa: BLE001
                        _health_svc.record_error(cid, str(exc), source_type=stype)
                        _probe_log.warning("probe %s: %s", cid, exc)
            await asyncio.sleep(300)  # 5 minutes

    _probe_task = asyncio.create_task(_periodic_health_probe())

    yield

    # Cancel background prober on shutdown
    _probe_task.cancel()
    try:
        await _probe_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="ARGUS — Multi-Domain Surveillance Intelligence",
    version="2.0.0",
    description="Multi-domain surveillance: ships, aircraft, satellites, events, and signals intelligence.",
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
# Audit logging — must be added AFTER CORS so CORS headers are present on audit path.
app.add_middleware(AuditLoggingMiddleware)
# Performance budget enforcement — zero blocking I/O, < 1ms overhead.
app.add_middleware(PerformanceBudgetMiddleware)

@app.get("/", include_in_schema=False)
def index() -> JSONResponse:
    return JSONResponse({"service": "ARGUS API", "docs": "/docs", "version": "2.0.0"})

from app.routers import (
    analyze,
    config_router,
    credits,
    health,
    health_connectors,
    jobs,
    providers_router,
    search,
    thumbnails,
    ws_jobs,
)
from app.routers import cache_stats as cache_stats_router_module

app.include_router(health.router)
app.include_router(health_connectors.router)
app.include_router(cache_stats_router_module.router)
app.include_router(config_router.router)
app.include_router(providers_router.router)
app.include_router(credits.router)
app.include_router(analyze.router)
app.include_router(jobs.router)
app.include_router(search.router)
app.include_router(ws_jobs.router)
app.include_router(thumbnails.router)

# ── V2 routes (P1-2, P1-3, P1-4, P1-5, P2-2, P2-3, P4-1, P4-2) ────────────
# ── Phase 5 Track D — Absence-As-Signal Analytics ───────────────────────────
from src.api import absence as absence_router_module
from src.api import airspace as airspace_router_module

# ── Phase 5 Track C — Agent-Assisted Analyst Workflows ──────────────────────
from src.api import analyst as analyst_router_module
from src.api import analytics as analytics_router_module
from src.api import aois as aois_router_module

# ── Phase 4 Track B — Camera/Video Abstraction routes ───────────────────────
from src.api import cameras as cameras_router_module

# ── P6 Maritime Intelligence routes ─────────────────────────────────────────
from src.api import chokepoints as chokepoints_router_module
from src.api import dark_ships as dark_ships_router_module
from src.api import detections as detections_router_module
from src.api import events as events_router_module

# ── Phase 5 Track B — Evidence Packs ────────────────────────────────────────
from src.api import evidence_packs as evidence_packs_router_module
from src.api import exports as exports_router_module
from src.api import imagery as imagery_router_module
from src.api import intel as intel_router_module

# ── Phase 5 Track A — Saved Investigations ──────────────────────────────────
from src.api import investigations as investigations_router_module
from src.api import jamming as jamming_router_module

# ── Phase 2 Operational Layer routes ────────────────────────────────────────
from src.api import orbits as orbits_router_module
from src.api import playback as playback_router_module
from src.api import source_health as source_health_router_module
from src.api import strike as strike_router_module
from src.api import vessels as vessels_router_module

app.include_router(aois_router_module.router)
app.include_router(events_router_module.router)
app.include_router(exports_router_module.router)
app.include_router(imagery_router_module.router)
app.include_router(playback_router_module.router)
app.include_router(analytics_router_module.router)
app.include_router(source_health_router_module.router)
app.include_router(chokepoints_router_module.router)
app.include_router(vessels_router_module.router)
app.include_router(dark_ships_router_module.router)
app.include_router(intel_router_module.router)
app.include_router(orbits_router_module.router)
app.include_router(airspace_router_module.router)
app.include_router(jamming_router_module.router)
app.include_router(strike_router_module.router)
app.include_router(cameras_router_module.router)
app.include_router(detections_router_module.router)
app.include_router(investigations_router_module.router)
app.include_router(absence_router_module.router)
app.include_router(evidence_packs_router_module.router)
app.include_router(analyst_router_module.router)

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
