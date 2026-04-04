"""Unit tests for app/rate_limiter.py and app/performance_budgets.py — Phase 6 Track B."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.rate_limiter import (
    RATE_LIMITS,
    WINDOW_SECONDS,
    SlidingWindowRateLimiter,
    UserRole,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def limiter() -> SlidingWindowRateLimiter:
    """Return a fresh rate limiter for each test."""
    return SlidingWindowRateLimiter()


# ── RATE_LIMITS constants ─────────────────────────────────────────────────────


def test_analyst_limit_is_60_per_minute() -> None:
    assert RATE_LIMITS[UserRole.ANALYST.value] == 60


def test_operator_limit_is_300_per_minute() -> None:
    assert RATE_LIMITS[UserRole.OPERATOR.value] == 300


def test_admin_limit_is_zero_ie_unlimited() -> None:
    assert RATE_LIMITS[UserRole.ADMIN.value] == 0


def test_demo_limit_is_120_per_minute() -> None:
    assert RATE_LIMITS["demo"] == 120


def test_window_is_60_seconds() -> None:
    assert WINDOW_SECONDS == 60.0


# ── is_allowed basic behaviour ────────────────────────────────────────────────


def test_first_request_is_allowed(limiter: SlidingWindowRateLimiter) -> None:
    allowed, retry_after = limiter.is_allowed("user1:path", limit=10)
    assert allowed is True
    assert retry_after == 0


def test_unlimited_zero_limit_always_allowed(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(1000):
        allowed, retry_after = limiter.is_allowed("admin:path", limit=0)
        assert allowed is True
        assert retry_after == 0


def test_limit_of_one_blocks_second_request(limiter: SlidingWindowRateLimiter) -> None:
    limiter.is_allowed("key", limit=1)  # first — allowed
    allowed, retry_after = limiter.is_allowed("key", limit=1)  # second — blocked
    assert allowed is False
    assert retry_after >= 1


def test_retry_after_is_positive_integer(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(5):
        limiter.is_allowed("k", limit=5)
    allowed, retry_after = limiter.is_allowed("k", limit=5)
    assert not allowed
    assert isinstance(retry_after, int)
    assert retry_after >= 1


def test_independent_keys_do_not_interfere(limiter: SlidingWindowRateLimiter) -> None:
    limiter.is_allowed("user-a:path", limit=1)  # fill user-a
    limiter.is_allowed("user-a:path", limit=1)  # user-a blocked
    # user-b should be unaffected
    allowed, _ = limiter.is_allowed("user-b:path", limit=1)
    assert allowed is True


# ── check() raises HTTP 429 ───────────────────────────────────────────────────


def test_check_raises_429_when_limit_exceeded(limiter: SlidingWindowRateLimiter) -> None:
    limiter.check("key", limit=1)  # first — allowed
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("key", limit=1)  # second — blocked
    assert exc_info.value.status_code == 429


def test_check_429_includes_retry_after_header(limiter: SlidingWindowRateLimiter) -> None:
    limiter.check("key", limit=1)
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("key", limit=1)
    assert "Retry-After" in exc_info.value.headers
    retry_after_val = int(exc_info.value.headers["Retry-After"])
    assert retry_after_val >= 1


def test_check_does_not_raise_when_under_limit(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(5):
        limiter.check("key", limit=10)  # should not raise


def test_check_admin_never_raises(limiter: SlidingWindowRateLimiter) -> None:
    for _ in range(500):
        limiter.check("admin", limit=0)  # limit=0 means unlimited


# ── Window expiry / reset ─────────────────────────────────────────────────────


def test_window_reset_allows_requests_after_expiry(limiter: SlidingWindowRateLimiter) -> None:
    """After the sliding window expires, the counter should reset."""
    # Patch WINDOW_SECONDS so we don't wait a full minute
    import app.rate_limiter as _rl_mod
    original = _rl_mod.WINDOW_SECONDS
    _rl_mod.WINDOW_SECONDS = 0.1  # 100 ms window
    try:
        lim = SlidingWindowRateLimiter()
        allowed, _ = lim.is_allowed("k", limit=1)
        assert allowed
        allowed2, _ = lim.is_allowed("k", limit=1)
        assert not allowed2  # blocked
        time.sleep(0.15)   # wait for window to expire
        allowed3, _ = lim.is_allowed("k", limit=1)
        assert allowed3   # window has reset
    finally:
        _rl_mod.WINDOW_SECONDS = original


def test_reset_clears_all_counters(limiter: SlidingWindowRateLimiter) -> None:
    limiter.is_allowed("a", limit=1)
    limiter.is_allowed("b", limit=1)
    limiter.reset()
    allowed, _ = limiter.is_allowed("a", limit=1)
    assert allowed


# ── Thread safety ─────────────────────────────────────────────────────────────


def test_concurrent_requests_respect_limit() -> None:
    """100 threads hit the same key against a limit of 50.
    Exactly 50 should be allowed; the rest blocked.
    """
    lim = SlidingWindowRateLimiter()
    results: list[bool] = []
    lock = threading.Lock()

    def make_request() -> None:
        allowed, _ = lim.is_allowed("shared", limit=50)
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=make_request) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed_count = sum(1 for r in results if r)
    blocked_count = sum(1 for r in results if not r)
    assert allowed_count == 50
    assert blocked_count == 50


# ── Performance budget counter ────────────────────────────────────────────────


def test_performance_budget_violation_increments_counter() -> None:
    """PerformanceBudgetMiddleware increments the violations counter."""
    from app import metrics as _metrics

    # Reset the counter bucket we'll use
    _metrics.reset_all()

    # Import the middleware and call dispatch directly via a minimal mock
    import asyncio
    from app.performance_budgets import (
        PerformanceBudgetMiddleware,
        MAX_BRIEFING_GENERATION_SECONDS,
    )
    from starlette.responses import Response as StarletteResponse
    from starlette.datastructures import URL

    middleware = PerformanceBudgetMiddleware(app=MagicMock())

    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/analyst/briefings"
    mock_request.url = MagicMock()
    mock_request.url.path = "/api/v1/analyst/briefings"

    slow_response = StarletteResponse(content=b"ok")
    call_count = {"n": 0}

    async def slow_next(req):
        # Simulate a slow response by sleeping past the budget
        await asyncio.sleep(MAX_BRIEFING_GENERATION_SECONDS + 0.05)
        return slow_response

    async def run():
        await middleware.dispatch(mock_request, slow_next)

    asyncio.run(run())

    snap = _metrics.snapshot()
    violations = snap["counters"].get(
        "performance_budget_violations_total{endpoint=/api/v1/analyst/briefings,reason=latency}",
        0,
    )
    assert violations >= 1


def test_performance_budget_no_violation_for_fast_response() -> None:
    """Fast responses must NOT increment the violations counter."""
    from app import metrics as _metrics
    _metrics.reset_all()

    import asyncio
    from app.performance_budgets import PerformanceBudgetMiddleware
    from starlette.responses import Response as StarletteResponse

    middleware = PerformanceBudgetMiddleware(app=MagicMock())

    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/analyst/briefings"

    fast_response = StarletteResponse(content=b"ok")

    async def fast_next(req):
        return fast_response

    async def run():
        await middleware.dispatch(mock_request, fast_next)

    asyncio.run(run())

    snap = _metrics.snapshot()
    # No counter with briefings violation should be present
    briefings_violations = {
        k: v
        for k, v in snap["counters"].items()
        if "performance_budget_violations_total" in k and "briefings" in k and "latency" in k
    }
    assert all(v == 0 for v in briefings_violations.values()) or not briefings_violations


def test_performance_budget_unmonitored_path_has_no_overhead() -> None:
    """Paths not in the budget map skip the timing logic."""
    import asyncio
    from app.performance_budgets import PerformanceBudgetMiddleware
    from starlette.responses import Response as StarletteResponse

    middleware = PerformanceBudgetMiddleware(app=MagicMock())
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/aois"

    response = StarletteResponse(content=b"ok")

    async def next_fn(req):
        return response

    async def run():
        return await middleware.dispatch(mock_request, next_fn)

    result = asyncio.run(run())
    assert result is response


# ── Cost guardrails ───────────────────────────────────────────────────────────


def test_cost_guardrail_briefing_quota_enforced() -> None:
    from app.cost_guardrails import _check_and_increment, reset_counters
    reset_counters()
    for _ in range(10):
        _check_and_increment("user-x", "briefing", max_count=10)
    with pytest.raises(HTTPException) as exc_info:
        _check_and_increment("user-x", "briefing", max_count=10)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_cost_guardrail_evidence_pack_quota_enforced() -> None:
    from app.cost_guardrails import _check_and_increment, reset_counters
    reset_counters()
    for _ in range(20):
        _check_and_increment("user-y", "evidence_pack", max_count=20)
    with pytest.raises(HTTPException) as exc_info:
        _check_and_increment("user-y", "evidence_pack", max_count=20)
    assert exc_info.value.status_code == 429


def test_cost_guardrail_unlimited_when_max_is_zero() -> None:
    from app.cost_guardrails import _check_and_increment, reset_counters
    reset_counters()
    for _ in range(200):
        _check_and_increment("admin-user", "briefing", max_count=0)  # should never raise


def test_cost_guardrail_different_users_are_independent() -> None:
    from app.cost_guardrails import _check_and_increment, reset_counters
    reset_counters()
    # Fill quota for user-1
    for _ in range(5):
        _check_and_increment("user-1", "briefing", max_count=5)
    # user-1 should now be blocked
    with pytest.raises(HTTPException):
        _check_and_increment("user-1", "briefing", max_count=5)
    # user-2 should be unaffected
    _check_and_increment("user-2", "briefing", max_count=5)  # no raise


def test_cost_guardrail_reset_clears_state() -> None:
    from app.cost_guardrails import _check_and_increment, reset_counters, get_counter
    reset_counters()
    for _ in range(3):
        _check_and_increment("user-z", "briefing", max_count=10)
    assert get_counter("user-z", "briefing") == 3
    reset_counters()
    assert get_counter("user-z", "briefing") == 0


def test_cost_guardrail_window_rollover() -> None:
    """After the 1-hour window expires, the counter should reset."""
    import app.cost_guardrails as _cg

    original = _cg._WINDOW
    _cg._WINDOW = 0.1  # 100ms for testing
    _cg.reset_counters()
    try:
        _cg._check_and_increment("rollover-user", "briefing", max_count=2)
        _cg._check_and_increment("rollover-user", "briefing", max_count=2)
        with pytest.raises(HTTPException):
            _cg._check_and_increment("rollover-user", "briefing", max_count=2)
        time.sleep(0.15)
        # After rollover, should be allowed again
        _cg._check_and_increment("rollover-user", "briefing", max_count=2)
    finally:
        _cg._WINDOW = original
