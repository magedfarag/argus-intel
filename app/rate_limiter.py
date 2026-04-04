"""Role-aware sliding-window rate limiter — Phase 6 Track B.

Self-contained implementation: no external dependencies beyond stdlib.
State is in-process per worker.  For multi-worker deployments, replace
the in-memory windows with Redis INCR/EXPIRE (e.g. via slowapi + redis).

Rate limits (requests per minute):
  analyst  role: 60
  operator role: 300
  admin    role: unlimited (0 = no limit)
  demo / unauthenticated: 120  (generous for demos)

Usage as a FastAPI dependency::

    from app.rate_limiter import heavy_endpoint_rate_limit

    @router.post("/expensive")
    def my_endpoint(_rl: None = Depends(heavy_endpoint_rate_limit)):
        ...
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status

from app.dependencies import UserClaims, UserRole, get_current_user

# ── Per-role request limits (requests / minute) ────────────────────────────────

RATE_LIMITS: Dict[str, int] = {
    UserRole.ANALYST.value: 60,
    UserRole.OPERATOR.value: 300,
    UserRole.ADMIN.value: 0,   # 0 = unlimited
    "demo": 120,               # unauthenticated / demo mode
}

WINDOW_SECONDS: float = 60.0


# ── Sliding-window counter ─────────────────────────────────────────────────────


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter.

    Each unique *key* (user_id + endpoint) gets its own deque of request
    timestamps.  Timestamps older than WINDOW_SECONDS are trimmed on every
    call so memory usage stays bounded.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key → deque of monotonic timestamps
        self._windows: Dict[str, Deque[float]] = {}

    def _trim(self, dq: Deque[float], now: float) -> None:
        """Remove timestamps that have fallen outside the sliding window."""
        cutoff = now - WINDOW_SECONDS
        while dq and dq[0] < cutoff:
            dq.popleft()

    def is_allowed(self, key: str, limit: int) -> Tuple[bool, int]:
        """Check whether the key is within its rate limit.

        Returns:
            (True, 0)            — request allowed; counter incremented.
            (False, retry_after) — limit exceeded; retry_after in seconds.

        If *limit* is 0, always returns (True, 0).
        """
        if limit == 0:
            return True, 0

        now = time.monotonic()
        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()
            dq = self._windows[key]
            self._trim(dq, now)
            count = len(dq)
            if count < limit:
                dq.append(now)
                return True, 0
            # Limit exceeded — compute soonest retry time
            oldest = dq[0]
            retry_after = math.ceil(WINDOW_SECONDS - (now - oldest))
            return False, max(1, retry_after)

    def check(self, key: str, limit: int) -> None:
        """Raise HTTP 429 if the rate limit for *key* is exceeded."""
        allowed, retry_after = self.is_allowed(key, limit)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        """Clear all counters (for testing)."""
        with self._lock:
            self._windows.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_limiter = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    """Return the process-wide rate limiter (injectable in tests)."""
    return _limiter


# ── FastAPI dependency ────────────────────────────────────────────────────────


def heavy_endpoint_rate_limit(
    request: Request,
    user: UserClaims = Depends(get_current_user),
) -> None:
    """FastAPI dependency — apply role-aware rate limiting to heavy endpoints.

    Applies the per-role limit from RATE_LIMITS.  Admin users bypass all
    limits (limit == 0).  Returns None on success; raises HTTP 429 on breach.

    Attach to heavy endpoints::

        @router.post("/expensive")
        def handler(_rl: None = Depends(heavy_endpoint_rate_limit)):
            ...
    """
    limit = RATE_LIMITS.get(user.role.value, RATE_LIMITS[UserRole.ANALYST.value])
    # Build a key scoped to user + path so different endpoints have independent windows
    key = f"rl:{user.user_id}:{request.url.path}"
    _limiter.check(key, limit)
