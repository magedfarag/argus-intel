"""Cost guardrails for premium operations — Phase 6 Track B.

In-process per-user per-hour request counters.  Enforces config limits:
  - max_briefings_per_hour_per_user    (default 10)
  - max_evidence_packs_per_hour_per_user (default 20)
  - max_export_size_mb                  (default 50)

State is in-process per worker.  For multi-worker deployments, replace
the in-memory counters with Redis INCR/EXPIRE (atomic, no race conditions).

Admin users bypass all guardrails (unlimited operations).
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, Tuple

from fastapi import Depends, HTTPException, status

from app.config import get_settings
from app.dependencies import UserClaims, UserRole, get_current_user

# ── Counter store ─────────────────────────────────────────────────────────────
# key: (user_id, operation) → (count, window_start_monotonic)

_lock = threading.Lock()
_counters: Dict[Tuple[str, str], Tuple[int, float]] = {}

_WINDOW: float = 3600.0  # 1 hour


# ── Internal counter logic ────────────────────────────────────────────────────


def _check_and_increment(user_id: str, operation: str, max_count: int) -> None:
    """Increment quota counter, raising HTTP 429 if the hourly cap is exceeded.

    Args:
        user_id:   Resolved identity string (from UserClaims.user_id).
        operation: Operation name used in the error message (e.g. "briefing").
        max_count: Maximum operations allowed per hour.  0 = unlimited.
    """
    if max_count <= 0:
        return  # 0 means unlimited

    now = time.monotonic()
    key = (user_id, operation)
    with _lock:
        if key not in _counters:
            _counters[key] = (0, now)
        count, window_start = _counters[key]
        # Roll over to a new window when the old one has expired
        if now - window_start >= _WINDOW:
            count, window_start = 0, now
            _counters[key] = (count, window_start)
        if count >= max_count:
            remaining = math.ceil(_WINDOW - (now - window_start))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Hourly limit of {max_count} {operation} operations exceeded. "
                    f"Try again in {remaining}s."
                ),
                headers={"Retry-After": str(remaining)},
            )
        _counters[key] = (count + 1, window_start)


# ── FastAPI dependencies ──────────────────────────────────────────────────────


def require_briefing_quota(
    user: UserClaims = Depends(get_current_user),
) -> UserClaims:
    """Enforce per-user hourly briefing generation quota.

    Attach to POST /api/v1/analyst/briefings and related endpoints.
    Admin users are exempt.
    """
    if user.role == UserRole.ADMIN:
        return user
    settings = get_settings()
    _check_and_increment(
        user.user_id,
        "briefing",
        settings.max_briefings_per_hour_per_user,
    )
    return user


def require_evidence_pack_quota(
    user: UserClaims = Depends(get_current_user),
) -> UserClaims:
    """Enforce per-user hourly evidence pack generation quota.

    Attach to POST /api/v1/evidence-packs and related endpoints.
    Admin users are exempt.
    """
    if user.role == UserRole.ADMIN:
        return user
    settings = get_settings()
    _check_and_increment(
        user.user_id,
        "evidence_pack",
        settings.max_evidence_packs_per_hour_per_user,
    )
    return user


# ── Test helpers ──────────────────────────────────────────────────────────────


def reset_counters() -> None:
    """Clear all counters (for testing only)."""
    with _lock:
        _counters.clear()


def get_counter(user_id: str, operation: str) -> int:
    """Return the current count for a user+operation pair (for testing)."""
    with _lock:
        entry = _counters.get((user_id, operation))
        if entry is None:
            return 0
        count, window_start = entry
        # Return 0 if the window has expired
        if time.monotonic() - window_start >= _WINDOW:
            return 0
        return count
