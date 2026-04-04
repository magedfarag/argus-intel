"""Celery application instance.

Import this module to get the celery_app instance for task registration
and control operations.  The broker and backend URLs are resolved at
import time from AppSettings so they respect .env files.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

try:
    from celery import Celery

    from app.config import get_settings

    settings = get_settings()
    broker   = settings.effective_celery_broker()
    backend  = settings.effective_celery_backend()

    if not broker:
        log.warning(
            "CELERY_BROKER_URL / REDIS_URL not set — "
            "Celery tasks will not be available until Redis is configured."
        )

    celery_app = Celery(
        "construction_monitor",
        broker=broker or "redis://localhost:6379/0",
        backend=backend or "redis://localhost:6379/0",
    )

    # P5-2.2: Three queues with explicit priority order.
    # Workers can elect which queues to consume (e.g. --queues=high,default).
    # Priority:  high (change-detection jobs)  >  default (polling)  >  low (exports)
    _QUEUE_CONFIG = {
        "high":    {"exchange": "high",    "routing_key": "high"},
        "default": {"exchange": "default", "routing_key": "default"},
        "low":     {"exchange": "low",     "routing_key": "low"},
    }

    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=86400,        # 24 h TTL on results
        task_track_started=True,
        worker_prefetch_multiplier=1,
        task_queues=_QUEUE_CONFIG,
        task_default_queue="default",
        # P5-2.2: Route tasks to queues by name
        task_routes={
            "run_analysis_task":                {"queue": "high"},
            "run_change_detection_task":        {"queue": "high"},
            "poll_gdelt_context":               {"queue": "default"},
            "poll_opensky_positions":           {"queue": "default"},
            "poll_aisstream_positions":         {"queue": "default"},
            "poll_rapidapi_ais":               {"queue": "default"},
            "poll_vessel_data":                {"queue": "default"},
            "enforce_telemetry_retention":      {"queue": "low"},
            "run_export_task":                  {"queue": "low"},
            "probe_stac_connectors":            {"queue": "default"},
            "workers.warm_playback_windows":    {"queue": "default"},
        },
        # P5-2.1: Beat schedules for all polling connectors:
        # P2-1.4 GDELT (15 min), P3-2.5 OpenSky (60 s), P3-1 AIS (30 s), P5-4.4 Retention (1 h)
        beat_schedule={
            "poll-gdelt-every-15min": {
                "task": "poll_gdelt_context",
                "schedule": 900.0,  # 15 minutes
                "options": {"queue": "default"},
            },
            "poll-opensky-every-60s": {
                "task": "poll_opensky_positions",
                "schedule": 60.0,   # 60 seconds — OpenSky free-tier friendly
                "options": {"queue": "default"},
            },
            "poll-aisstream-every-30s": {
                "task": "poll_aisstream_positions",
                "schedule": 30.0,   # 30 seconds — bounded by AIS WS collect_timeout_s
                "options": {"queue": "default"},
            },
            "poll-rapidapi-ais": {
                "task": "poll_rapidapi_ais",
                "schedule": float(settings.rapid_api_poll_interval),
                "options": {"queue": "default"},
            },
            "poll-vessel-data": {
                "task": "poll_vessel_data",
                "schedule": float(settings.vessel_data_poll_interval),
                "options": {"queue": "default"},
            },
            "enforce-telemetry-retention-every-hour": {
                "task": "enforce_telemetry_retention",
                "schedule": float(settings.retention_enforcement_interval_seconds),
                "options": {"queue": "low"},
            },
            "probe-stac-connectors-every-5min": {
                "task": "probe_stac_connectors",
                "schedule": 300.0,  # 5 minutes — lightweight GET to STAC roots
                "options": {"queue": "default"},
            },
            "warm-playback-windows-every-6h": {
                "task": "workers.warm_playback_windows",
                "schedule": 21600.0,  # 6 hours — reasonable for 24h/7d/30d windows
                "options": {"queue": "default"},
            },
        },
        beat_schedule_filename="celerybeat-schedule",
    )

except ImportError:
    log.error("celery package not installed — async jobs disabled")
    celery_app = None  # type: ignore[assignment]
