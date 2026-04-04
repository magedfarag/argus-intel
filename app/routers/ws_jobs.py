"""WebSocket endpoint for live job progress streaming.

Replaces 3-second polling with server-push over WebSocket.
Client connects to ws://host/api/jobs/{job_id}/stream and receives
JSON messages with job state updates until completion or failure.

Falls back gracefully: if Celery/Redis is not configured, immediately
sends an error frame and closes the connection.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["websocket"])

_POLL_INTERVAL = 0.5  # seconds between Celery status checks


@router.websocket("/jobs/{job_id}/stream")
async def job_stream(websocket: WebSocket, job_id: str) -> None:
    """Stream job progress via WebSocket until terminal state."""
    await websocket.accept()

    settings = get_settings()
    if not settings.effective_celery_broker():
        await websocket.send_json({
            "type": "error",
            "message": "Async jobs require Redis / Celery. See REDIS_URL in .env.example.",
        })
        await websocket.close(code=1008)
        return

    try:
        from celery.result import AsyncResult
        from app.workers.celery_app import celery_app
    except ImportError:
        await websocket.send_json({
            "type": "error",
            "message": "Celery is not installed.",
        })
        await websocket.close(code=1008)
        return

    previous_state: Optional[str] = None

    try:
        while True:
            res = AsyncResult(job_id, app=celery_app)
            current_state = res.state.lower()

            # Only send updates when state changes
            if current_state != previous_state:
                previous_state = current_state

                if current_state == "success":
                    raw = res.result
                    result_data = None
                    if isinstance(raw, dict):
                        result_data = raw
                    await websocket.send_json({
                        "type": "completed",
                        "job_id": job_id,
                        "state": "completed",
                        "result": result_data,
                    })
                    await websocket.close(code=1000)
                    return

                elif current_state == "failure":
                    await websocket.send_json({
                        "type": "failed",
                        "job_id": job_id,
                        "state": "failed",
                        "error": str(res.result),
                    })
                    await websocket.close(code=1000)
                    return

                elif current_state == "revoked":
                    await websocket.send_json({
                        "type": "cancelled",
                        "job_id": job_id,
                        "state": "cancelled",
                    })
                    await websocket.close(code=1000)
                    return

                else:
                    await websocket.send_json({
                        "type": "progress",
                        "job_id": job_id,
                        "state": current_state,
                    })

            await asyncio.sleep(_POLL_INTERVAL)

    except WebSocketDisconnect:
        log.debug("Client disconnected from job stream %s", job_id)
    except Exception as exc:
        log.warning("WebSocket error for job %s: %s", job_id, exc)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(exc),
            })
            await websocket.close(code=1011)
        except Exception:
            pass