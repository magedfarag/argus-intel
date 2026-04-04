"""Celery tasks for async analysis execution."""
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

try:
    from app.workers.celery_app import celery_app
    if celery_app is None:
        raise ImportError("celery_app is None")

    @celery_app.task(bind=True, name="run_analysis_task")
    def run_analysis_task(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a full analysis and return the serialised AnalyzeResponse."""
        from app.config import get_settings
        from app.cache.client import CacheClient
        from app.providers.demo import DemoProvider
        from app.providers.registry import ProviderRegistry
        from app.models.requests import AnalyzeRequest
        from app.services.analysis import AnalysisService

        settings = get_settings()
        cache    = CacheClient.from_settings(settings)

        # Build minimal registry for worker process
        registry = ProviderRegistry()
        registry.register(DemoProvider())

        # Register live providers if configured
        if settings.sentinel2_is_configured():
            try:
                from app.providers.sentinel2 import Sentinel2Provider
                registry.register(Sentinel2Provider(settings))
            except Exception as exc:
                log.warning("Sentinel2Provider unavailable in worker: %s", exc)

        if settings.landsat_is_configured():
            try:
                from app.providers.landsat import LandsatProvider
                registry.register(LandsatProvider(settings))
            except Exception as exc:
                log.warning("LandsatProvider unavailable in worker: %s", exc)

        svc     = AnalysisService(registry=registry, cache=cache, settings=settings)
        request = AnalyzeRequest(**request_json)
        result  = svc.run_sync(request)
        return result.model_dump(mode="json")

    @celery_app.task(name="poll_gdelt_context")
    def poll_gdelt_context() -> Dict[str, Any]:
        """P2-1.4: 15-minute GDELT polling task.

        Fetches the latest GDELT contextual events for all active AOIs and
        normalizes them into CanonicalEvents.  Uses the in-memory AOI store
        until PostGIS persistence is wired (P0-4).

        Returns a summary dict: {polled_at, aoi_count, article_count, errors}.
        """
        from datetime import datetime, timedelta, timezone

        from src.connectors.gdelt import GdeltConnector, DEFAULT_CONSTRUCTION_THEMES
        from src.services.aoi_store import AoiStore

        polled_at = datetime.now(timezone.utc).isoformat()
        aoi_store = AoiStore()
        connector = GdeltConnector(default_themes=DEFAULT_CONSTRUCTION_THEMES)

        aois = aoi_store.list_aois()
        article_count = 0
        errors: list = []

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=30)  # overlap window

        for aoi in aois:
            try:
                geometry = aoi.get("geometry") or {}
                if not geometry:
                    continue
                raw_articles = connector.fetch(
                    geometry, start_time, end_time, max_results=50
                )
                events = connector.normalize_all(raw_articles)
                article_count += len(events)
                log.info(
                    "poll_gdelt_context: AOI %s → %d events",
                    aoi.get("id", "unknown"),
                    len(events),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("poll_gdelt_context: AOI poll failed — %s", exc)
                errors.append(str(exc))

        return {
            "polled_at": polled_at,
            "aoi_count": len(aois),
            "article_count": article_count,
            "errors": errors,
        }

    @celery_app.task(name="poll_opensky_positions")
    def poll_opensky_positions() -> Dict[str, Any]:
        """P3-2.5: 60-second OpenSky aviation polling task.

        Fetches state vectors for all active AOIs and normalises them
        into aircraft_position CanonicalEvents.
        Returns a summary dict: {polled_at, aoi_count, aircraft_count, errors}.
        """
        import os
        from datetime import datetime, timedelta, timezone

        from src.connectors.opensky import OpenSkyConnector
        from src.services.aoi_store import AoiStore

        polled_at = datetime.now(timezone.utc).isoformat()
        connector = OpenSkyConnector(
            username=os.getenv("OPENSKY_USERNAME", ""),
            password=os.getenv("OPENSKY_PASSWORD", ""),
        )
        aoi_store = AoiStore()
        aois = aoi_store.list_aois()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=2)
        aircraft_count = 0
        errors: list = []

        for aoi in aois:
            try:
                geometry = aoi.get("geometry") or {}
                if not geometry:
                    continue
                raw_states = connector.fetch(geometry, start_time, end_time)
                events = connector.normalize_all(raw_states)
                aircraft_count += len(events)
                log.info(
                    "poll_opensky_positions: AOI %s → %d aircraft",
                    aoi.get("id", "unknown"),
                    len(events),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("poll_opensky_positions: AOI poll failed — %s", exc)
                errors.append(str(exc))

        return {
            "polled_at": polled_at,
            "aoi_count": len(aois),
            "aircraft_count": aircraft_count,
            "errors": errors,
        }

    @celery_app.task(name="poll_aisstream_positions")
    def poll_aisstream_positions() -> Dict[str, Any]:
        """P5-2.1: 30-second AIS maritime polling task.

        Fetches ship positions for all active AOIs via AISStream.io WebSocket.
        The connector is bounded by collect_timeout_s to avoid blocking.
        Returns a summary dict: {polled_at, aoi_count, ship_count, errors}.
        """
        import os
        from datetime import datetime, timezone

        from src.connectors.ais_stream import AisStreamConnector
        from src.services.aoi_store import AoiStore
        from src.services.source_health import get_health_service

        api_key = os.getenv("AISSTREAM_API_KEY", "")
        if not api_key:
            return {"polled_at": datetime.now(timezone.utc).isoformat(), "skipped": True}

        polled_at = datetime.now(timezone.utc).isoformat()
        health_svc = get_health_service()
        connector = AisStreamConnector(api_key=api_key, collect_timeout_s=25)
        aoi_store = AoiStore()
        aois = aoi_store.list_aois()
        ship_count = 0
        errors: list = []

        for aoi in aois:
            try:
                geometry = aoi.get("geometry") or {}
                if not geometry:
                    continue
                import asyncio
                raw_msgs = asyncio.run(connector.fetch_async(geometry, max_messages=100))
                events = connector.normalize_all(raw_msgs)
                ship_count += len(events)
                health_svc.record_success(
                    connector.connector_id,
                    connector.display_name,
                    connector.source_type,
                )
                log.info(
                    "poll_aisstream_positions: AOI %s → %d ship events",
                    aoi.get("id", "unknown"),
                    len(events),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("poll_aisstream_positions: AOI poll failed — %s", exc)
                errors.append(str(exc))
                health_svc.record_error(connector.connector_id, str(exc))

        return {
            "polled_at": polled_at,
            "aoi_count": len(aois),
            "ship_count": ship_count,
            "errors": errors,
        }

    @celery_app.task(name="poll_rapidapi_ais")
    def poll_rapidapi_ais() -> Dict[str, Any]:
        """Poll vessel positions via a configurable RapidAPI AIS endpoint.

        Uses the bbox defined by RAPID_API_SOUTH/WEST/NORTH/EAST when no AOIs
        are stored, otherwise queries per-AOI.  Writes results into the
        in-memory TelemetryStore.
        Returns: {polled_at, aoi_count, ship_count, errors}.
        """
        from datetime import datetime, timezone

        from app.config import get_settings
        from src.connectors.rapidapi_ais import RapidApiAisConnector
        from src.services.telemetry_store import TelemetryStore
        from src.services.source_health import get_health_service

        settings = get_settings()
        polled_at = datetime.now(timezone.utc).isoformat()
        connector = RapidApiAisConnector(
            api_key=settings.rapid_api_key,
            host=settings.rapid_api_host,
            south=settings.rapid_api_south,
            west=settings.rapid_api_west,
            north=settings.rapid_api_north,
            east=settings.rapid_api_east,
        )
        if not settings.rapid_api_is_configured():
            log.debug("poll_rapidapi_ais: RAPID_API_KEY not configured, skipping")
            return {"polled_at": polled_at, "aoi_count": 0, "ship_count": 0, "errors": 0}

        store = TelemetryStore()
        ship_count = 0
        errors = 0

        try:
            records = connector.fetch()
            events = connector.normalize_all(records)
            for ev in events:
                store.upsert(ev)
            ship_count += len(events)
            get_health_service().record_success(
                "rapidapi-ais", "RapidAPI AIS", "rapidapi"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("poll_rapidapi_ais: fetch failed — %s", exc)
            get_health_service().record_error("rapidapi-ais", str(exc))
            errors += 1

        log.info("poll_rapidapi_ais: %d ship events (%d errors)", ship_count, errors)
        return {"polled_at": polled_at, "aoi_count": 1, "ship_count": ship_count, "errors": errors}

    @celery_app.task(name="poll_vessel_data")
    def poll_vessel_data() -> Dict[str, Any]:
        """Poll vessel positions from vessel-data.p.rapidapi.com.

        Uses the centre+radius derived from VESSEL_DATA_SOUTH/WEST/NORTH/EAST.
        Writes results into the in-memory TelemetryStore.
        Returns: {polled_at, aoi_count, ship_count, errors}.
        """
        from datetime import datetime, timezone

        from app.config import get_settings
        from src.connectors.vessel_data import VesselDataConnector
        from src.services.telemetry_store import TelemetryStore
        from src.services.source_health import get_health_service

        settings = get_settings()
        polled_at = datetime.now(timezone.utc).isoformat()
        connector = VesselDataConnector(
            api_key=settings.vessel_data_api_key,
            south=settings.vessel_data_south,
            west=settings.vessel_data_west,
            north=settings.vessel_data_north,
            east=settings.vessel_data_east,
        )

        if not settings.vessel_data_is_configured():
            log.debug("poll_vessel_data: VESSEL_DATA_API_KEY not configured, skipping")
            return {"polled_at": polled_at, "aoi_count": 0, "ship_count": 0, "errors": 0}

        store = TelemetryStore()
        ship_count = 0
        errors = 0

        try:
            records = connector.fetch()
            events = connector.normalize_all(records)
            for ev in events:
                store.upsert(ev)
            ship_count += len(events)
            get_health_service().record_success(
                "vessel-data", "VesselData", "rapidapi"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("poll_vessel_data: fetch failed — %s", exc)
            get_health_service().record_error("vessel-data", str(exc))
            errors += 1

        log.info("poll_vessel_data: %d ship events (%d errors)", ship_count, errors)
        return {"polled_at": polled_at, "aoi_count": 1, "ship_count": ship_count, "errors": errors}

    @celery_app.task(name="enforce_telemetry_retention")
    def enforce_telemetry_retention() -> Dict[str, Any]:
        """P5-4.4: Automated data retention enforcement task.

        Prunes ship/aircraft telemetry to the configured retention policy.
        Runs via Celery beat on a configurable interval (default: 1 hour).
        Returns a summary dict: {enforced_at, entities_pruned, events_pruned}.
        """
        from datetime import datetime, timezone

        from src.services.telemetry_store import RetentionPolicy, TelemetryStore
        from src.services.source_health import get_health_service

        enforced_at = datetime.now(timezone.utc).isoformat()
        store = TelemetryStore()        # Uses the module-level in-memory store
        policy = RetentionPolicy()      # Uses defaults (max_age_days=30)

        try:
            result = store.enforce_retention(policy)
            store.thin_old_positions(policy)
            log.info(
                "enforce_telemetry_retention: pruned %d events across %d entities",
                result.get("events_pruned", 0),
                result.get("entities_pruned", 0),
            )
            get_health_service().record_success(
                "telemetry-retention", "Telemetry Retention", "internal"
            )
            return {"enforced_at": enforced_at, **result}
        except Exception as exc:  # noqa: BLE001
            log.error("enforce_telemetry_retention failed: %s", exc)
            get_health_service().record_error("telemetry-retention", str(exc))
            return {"enforced_at": enforced_at, "error": str(exc)}

except (ImportError, Exception) as exc:
    log.warning("Celery tasks not registered: %s", exc)

    def run_analysis_task(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")

    def poll_gdelt_context(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")

    def poll_opensky_positions(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")

    def poll_aisstream_positions(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")

    def poll_rapidapi_ais(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")

    def poll_vessel_data(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")

    def enforce_telemetry_retention(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery is not configured")
