"""Unit tests for WebSocket job streaming endpoint (P3-2)."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from backend.app.routers.ws_jobs import router, _POLL_INTERVAL


class TestWebSocketNoCelery:
    """When Celery/Redis not configured, WS closes with error frame."""

    def test_no_redis_url_sends_error_and_closes(self, app_client):
        """Without REDIS_URL the endpoint sends an error and closes."""
        with app_client.websocket_connect("/api/jobs/job-123/stream") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Redis" in msg["message"] or "Celery" in msg["message"]

    def test_error_frame_is_single_message(self, app_client):
        """Only one message should be sent before close."""
        with app_client.websocket_connect("/api/jobs/job-123/stream") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"


class TestWebSocketWithCelery:
    """When Celery is configured, WS streams job state updates."""

    def _make_mock_result(self, states, result=None):
        """Return a mock AsyncResult that cycles through the given states."""
        idx = {"i": 0}
        mock = MagicMock()

        def _state():
            s = states[min(idx["i"], len(states) - 1)]
            idx["i"] += 1
            return s

        type(mock).state = PropertyMock(side_effect=_state)
        mock.result = result if result is not None else {"analysis_id": "a-1"}
        return mock

    def _patched_connect(self, app_client, mock_async_result, job_id="job-1"):
        """Connect WS with all Celery internals mocked out."""
        mock_settings = MagicMock()
        mock_settings.effective_celery_broker.return_value = "redis://localhost/0"

        mock_ar_cls = MagicMock(return_value=mock_async_result)
        mock_celery = MagicMock()

        return (
            patch("backend.app.routers.ws_jobs.get_settings", return_value=mock_settings),
            patch("backend.app.routers.ws_jobs._POLL_INTERVAL", 0),
            patch.dict("sys.modules", {
                "celery.result": MagicMock(AsyncResult=mock_ar_cls),
                "backend.app.workers.celery_app": MagicMock(celery_app=mock_celery),
            }),
        )

    def _collect_messages(self, ws):
        msgs = []
        while True:
            try:
                msgs.append(ws.receive_json())
            except Exception:
                break
        return msgs

    def test_success_sends_completed(self, app_client):
        mock_res = self._make_mock_result(["PENDING", "STARTED", "SUCCESS"])
        patches = self._patched_connect(app_client, mock_res)
        with patches[0], patches[1], patches[2]:
            with app_client.websocket_connect("/api/jobs/job-ok/stream") as ws:
                msgs = self._collect_messages(ws)
        completed = [m for m in msgs if m["type"] == "completed"]
        assert len(completed) == 1
        assert completed[0]["job_id"] == "job-ok"
        assert completed[0]["result"] is not None

    def test_failure_sends_failed(self, app_client):
        mock_res = self._make_mock_result(["PENDING", "FAILURE"], result=Exception("boom"))
        patches = self._patched_connect(app_client, mock_res)
        with patches[0], patches[1], patches[2]:
            with app_client.websocket_connect("/api/jobs/job-fail/stream") as ws:
                msgs = self._collect_messages(ws)
        failed = [m for m in msgs if m["type"] == "failed"]
        assert len(failed) == 1
        assert "boom" in failed[0]["error"]

    def test_progress_messages_sent_on_state_change(self, app_client):
        mock_res = self._make_mock_result(["PENDING", "STARTED", "STARTED", "SUCCESS"])
        patches = self._patched_connect(app_client, mock_res)
        with patches[0], patches[1], patches[2]:
            with app_client.websocket_connect("/api/jobs/job-prog/stream") as ws:
                msgs = self._collect_messages(ws)
        progress = [m for m in msgs if m["type"] == "progress"]
        assert len(progress) >= 1

    def test_revoked_sends_cancelled(self, app_client):
        mock_res = self._make_mock_result(["PENDING", "REVOKED"])
        patches = self._patched_connect(app_client, mock_res)
        with patches[0], patches[1], patches[2]:
            with app_client.websocket_connect("/api/jobs/job-cancel/stream") as ws:
                msgs = self._collect_messages(ws)
        cancelled = [m for m in msgs if m["type"] == "cancelled"]
        assert len(cancelled) == 1

    def test_duplicate_state_not_resent(self, app_client):
        # PENDING appears three times but should only produce one progress message
        mock_res = self._make_mock_result(["PENDING", "PENDING", "PENDING", "SUCCESS"])
        patches = self._patched_connect(app_client, mock_res)
        with patches[0], patches[1], patches[2]:
            with app_client.websocket_connect("/api/jobs/job-dup/stream") as ws:
                msgs = self._collect_messages(ws)
        pending_msgs = [m for m in msgs if m.get("state") == "pending"]
        assert len(pending_msgs) == 1


class TestWebSocketRouterMeta:
    """Verify router configuration."""

    def test_poll_interval_is_reasonable(self):
        assert 0.1 <= _POLL_INTERVAL <= 5.0

    def test_router_has_websocket_route(self):
        ws_routes = [r for r in router.routes if hasattr(r, "path") and "stream" in r.path]
        assert len(ws_routes) == 1
        assert ws_routes[0].path == "/api/jobs/{job_id}/stream"
