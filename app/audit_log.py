"""Append-only audit logging for ARGUS — Phase 6 Track A.

An ``argus.audit`` logger records every instrumented mutation as a JSON line:

    {
        "action": "POST /api/v1/investigations",
        "user_id": "<sha256-prefix>",
        "resource_type": "investigation",
        "resource_id": "/api/v1/investigations/abc123",
        "timestamp": "2026-04-04T12:00:00+00:00",
        "ip_address": "127.0.0.1",
        "result": "success"
    }

The ``AuditLoggingMiddleware`` intercepts mutations at instrumented path
prefixes and writes the record *after* the upstream handler returns, so audit
logging does not add latency to the happy path (the record is written while the
response is being streamed to the client via a Starlette BackgroundTask).
"""
from __future__ import annotations

import hashlib
import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Callable

from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── Dedicated audit logger ─────────────────────────────────────────────────


_audit_logger = logging.getLogger("argus.audit")


def configure_audit_logger() -> None:
    """Attach a JSON-formatting StreamHandler to ``argus.audit`` if needed.

    Called once from ``app/main.py`` after ``configure_logging()``.  The
    handler is only added when the logger has no handlers yet so repeated calls
    (e.g. in tests) are safe.
    """
    if _audit_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(_AuditJsonFormatter())
    _audit_logger.addHandler(handler)
    _audit_logger.setLevel(logging.INFO)
    # Do not propagate to root — audit records must not appear in app logs.
    _audit_logger.propagate = False


class _AuditJsonFormatter(logging.Formatter):
    """Emit each audit record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # The record message is already a JSON string (see _write_audit).
        return record.getMessage()


# ── Core write helper ─────────────────────────────────────────────────────


def _hash_user_id(user_id: str) -> str:
    """Return the first 16 hex chars of SHA-256(user_id) for PII reduction."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def _write_audit(
    *,
    action: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    ip_address: str,
    result: str,
) -> None:
    """Serialise and emit one audit record."""
    record = {
        "action": action,
        "user_id": _hash_user_id(user_id),
        "resource_type": resource_type,
        "resource_id": resource_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": ip_address,
        "result": result,
    }
    _audit_logger.info(json.dumps(record, separators=(",", ":")))


# ── Path-to-resource helpers ──────────────────────────────────────────────


def _resource_type_from_path(path: str) -> str:
    """Derive a short resource type label from a URL path segment."""
    segments = [s for s in path.strip("/").split("/") if s]
    # Skip the api/v1 prefix
    api_idx = next(
        (i for i, s in enumerate(segments) if s.startswith("v")), -1
    )
    if api_idx >= 0 and api_idx + 1 < len(segments):
        return segments[api_idx + 1]
    return segments[-1] if segments else "unknown"


# ── Instrumented path prefixes ────────────────────────────────────────────
#
# Tuples of (HTTP_METHOD, path_prefix).  A request matches if both the method
# and the start of the URL path agree.

_AUDIT_TARGETS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/investigations"),
        ("PUT", "/api/v1/investigations/"),
        ("DELETE", "/api/v1/investigations/"),
        ("POST", "/api/v1/strikes/"),
        ("POST", "/api/v1/analyst/briefings"),
        ("POST", "/api/v1/absence/signals"),
        ("POST", "/api/v1/absence/scan/"),
        ("POST", "/api/v1/evidence-packs"),
    }
)


def _should_audit(method: str, path: str) -> bool:
    for target_method, target_prefix in _AUDIT_TARGETS:
        if method == target_method and path.startswith(target_prefix):
            return True
    return False


# ── ASGI middleware ───────────────────────────────────────────────────────


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that appends audit records for instrumented paths.

    The record is written via a ``BackgroundTask`` attached to the response so
    that audit I/O does not block response streaming to the client.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        if not _should_audit(request.method, request.url.path):
            return response

        # Capture values before the coroutine frame is torn down.
        user_id: str = getattr(request.state, "current_user_id", None) or "anonymous"
        ip_address: str = (
            request.client.host if request.client else "unknown"
        )
        result: str = "success" if response.status_code < 400 else "denied"
        action: str = f"{request.method} {request.url.path}"
        resource_type: str = _resource_type_from_path(request.url.path)
        resource_id: str = request.url.path

        audit_task = BackgroundTask(
            _write_audit,
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            result=result,
        )

        # Chain with any existing background task on the response.
        if response.background is None:
            response.background = audit_task
        else:
            existing: BackgroundTask = response.background  # type: ignore[assignment]
            chained = BackgroundTask(_chain_tasks, existing, audit_task)
            response.background = chained

        return response


async def _chain_tasks(first: BackgroundTask, second: BackgroundTask) -> None:
    """Run two BackgroundTasks sequentially."""
    await first()
    await second()
