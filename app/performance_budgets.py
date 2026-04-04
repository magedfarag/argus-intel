"""Performance budget constants and enforcement middleware — Phase 6 Track B.

Logs a WARNING and increments ``performance_budget_violations_total`` in
``app/metrics`` when an endpoint's response time or payload size exceeds its
defined budget.

Design goals:
  - < 1ms overhead per request (no blocking I/O, no disk writes).
  - Opt-in: only monitored paths pay the path-lookup cost.
  - Uses Content-Length header for size checks — never buffers the body.
"""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app import metrics

logger = logging.getLogger(__name__)

# ── Budget constants ───────────────────────────────────────────────────────────

MAX_REPLAY_QUERY_SECONDS: float = 3.0
MAX_EVIDENCE_PACK_EXPORT_SECONDS: float = 10.0
MAX_BRIEFING_GENERATION_SECONDS: float = 5.0
MAX_PLAYBACK_RESPONSE_BYTES: int = 5_000_000  # 5 MB payload cap

# ── Path-prefix → timing budget mapping ───────────────────────────────────────
# Order matters: more-specific prefixes first.

_PATH_BUDGETS: list[tuple[str, float]] = [
    ("/api/v1/analyst/briefings", MAX_BRIEFING_GENERATION_SECONDS),
    ("/api/v1/evidence-packs", MAX_EVIDENCE_PACK_EXPORT_SECONDS),
    ("/api/v1/playback/", MAX_REPLAY_QUERY_SECONDS),
    ("/api/v1/absence/scan", MAX_REPLAY_QUERY_SECONDS),
]


def _get_budget(path: str) -> Optional[float]:
    """Return timing budget in seconds for *path*, or None if unmonitored."""
    for prefix, budget in _PATH_BUDGETS:
        if path.startswith(prefix):
            return budget
    return None


# ── Middleware ─────────────────────────────────────────────────────────────────


class PerformanceBudgetMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that logs and counts performance budget violations.

    Timing is measured from just before ``call_next`` to just after — it
    reflects the full server-side processing time excluding network I/O between
    client and server.  The implementation adds at most one ``time.perf_counter()``
    call per request (for unmonitored paths the budget lookup returns None and
    the middleware returns immediately without timing).
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        budget = _get_budget(request.url.path)

        if budget is None:
            # Fast path: not a monitored endpoint
            return await call_next(request)

        # Timed path ──────────────────────────────────────────────────────────
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        if duration > budget:
            endpoint = request.url.path
            logger.warning(
                "Performance budget exceeded | endpoint=%s duration=%.3fs budget=%.1fs",
                endpoint,
                duration,
                budget,
            )
            metrics.increment(
                "performance_budget_violations_total",
                labels={"endpoint": endpoint, "reason": "latency"},
            )

        # Payload size check via Content-Length header (zero body buffering) ──
        if request.url.path.startswith("/api/v1/playback/"):
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    if size > MAX_PLAYBACK_RESPONSE_BYTES:
                        logger.warning(
                            "Playback response size budget exceeded | endpoint=%s "
                            "size=%d budget=%d",
                            request.url.path,
                            size,
                            MAX_PLAYBACK_RESPONSE_BYTES,
                        )
                        metrics.increment(
                            "performance_budget_violations_total",
                            labels={
                                "endpoint": request.url.path,
                                "reason": "size",
                            },
                        )
                except ValueError:
                    pass

        return response
