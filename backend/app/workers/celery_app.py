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

    from backend.app.config import get_settings

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
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=86400,        # 24 h TTL on results
        task_track_started=True,
        worker_prefetch_multiplier=1,
    )
    
    # Auto-discover tasks from this package
    celery_app.autodiscover_tasks(["backend.app.workers"])
    
    # Explicitly import tasks to ensure they're registered
    try:
        from backend.app.workers import tasks  # noqa: F401
    except ImportError as e:
        log.error("Failed to import tasks module: %s", e)

except ImportError:
    log.error("celery package not installed — async jobs disabled")
    celery_app = None  # type: ignore[assignment]
