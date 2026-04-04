"""Phase 1 Track C: Tests for playback window pre-warming via Celery beat task.

Covers:
  - warm_playback_windows is registered in the Celery app task registry
  - Calling warm_playback_windows() directly materializes one job per window (3 total)
"""
from __future__ import annotations

import pytest


def test_warm_playback_windows_registered_in_celery() -> None:
    """warm_playback_windows must appear in the Celery app task registry."""
    from app.workers.celery_app import celery_app
    import app.workers.tasks  # noqa: F401 — importing registers all tasks with celery_app

    if celery_app is None:
        pytest.skip("Celery not configured in this environment")

    assert "workers.warm_playback_windows" in celery_app.tasks, (
        "Task 'workers.warm_playback_windows' not found in celery_app.tasks — "
        "check that the task is decorated with @celery_app.task(name=...) inside "
        "the try block in app/workers/tasks.py"
    )


def test_warm_playback_windows_materializes_3_jobs() -> None:
    """Calling warm_playback_windows() directly enqueues one job per window (24h, 7d, 30d)."""
    from unittest.mock import patch

    from src.services.event_store import EventStore
    from src.services.playback_service import PlaybackService
    from app.workers.tasks import warm_playback_windows

    fresh_svc = PlaybackService(EventStore())
    with patch("src.api.playback.get_playback_service", return_value=fresh_svc):
        warm_playback_windows()

    assert len(fresh_svc._jobs) == 3, (
        f"Expected 3 materialization jobs (24h, 7d, 30d), got {len(fresh_svc._jobs)}"
    )
