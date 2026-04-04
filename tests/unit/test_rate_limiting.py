"""Unit tests for rate limiting (P2-5 — slowapi rate limits)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.resilience.rate_limiter import (
    limiter,
    rate_limit_error_handler,
    ANALYZE_RATE_LIMIT,
    SEARCH_RATE_LIMIT,
    JOBS_RATE_LIMIT,
)
from slowapi.errors import RateLimitExceeded


def test_rate_limit_constants_defined():
    """Test that rate limit constants are defined."""
    assert ANALYZE_RATE_LIMIT == "5/minute"
    assert SEARCH_RATE_LIMIT == "10/minute"
    assert JOBS_RATE_LIMIT == "20/minute"


def test_limiter_instance_created():
    """Test that slowapi Limiter is instantiated."""
    assert limiter is not None
    # Limiter should be a Limiter instance
    from slowapi.extension import Limiter as SlowAPILimiter
    assert isinstance(limiter, SlowAPILimiter)


def test_rate_limit_error_handler_returns_429():
    """Test that rate limit error handler returns HTTP 429."""
    mock_request = MagicMock(spec=Request)
    mock_exc = MagicMock(spec=RateLimitExceeded)
    mock_exc.detail = "5 per 1 minute"

    response = rate_limit_error_handler(mock_request, mock_exc)

    assert isinstance(response, JSONResponse)
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_rate_limit_error_handler_response_structure():
    """Test that rate limit error response has proper structure."""
    mock_request = MagicMock(spec=Request)
    mock_exc = MagicMock(spec=RateLimitExceeded)
    mock_exc.detail = "5 per 1 minute"

    response = rate_limit_error_handler(mock_request, mock_exc)

    # Response should be JSON with structured error
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    # Content should be dict (FastAPI will serialize to JSON)
    response_content = response.body.decode()
    assert "rate_limit_exceeded" in response_content or "Rate limit exceeded" in response_content


def test_rate_limit_error_includes_detail():
    """Test that error response includes rate limit detail."""
    mock_request = MagicMock(spec=Request)
    mock_exc = MagicMock(spec=RateLimitExceeded)
    mock_exc.detail = "10 per 1 minute"

    response = rate_limit_error_handler(mock_request, mock_exc)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    response_content = response.body.decode()
    assert "10 per 1 minute" in response_content


def test_analyze_rate_limit_lower_than_search():
    """Test that /analyze rate limit is stricter than /search."""
    # Parse: "5/minute" -> 5, "10/minute" -> 10
    analyze_limit = int(ANALYZE_RATE_LIMIT.split("/")[0])
    search_limit = int(SEARCH_RATE_LIMIT.split("/")[0])
    assert analyze_limit < search_limit


def test_search_rate_limit_lower_than_jobs():
    """Test that /search rate limit is stricter than /jobs."""
    search_limit = int(SEARCH_RATE_LIMIT.split("/")[0])
    jobs_limit = int(JOBS_RATE_LIMIT.split("/")[0])
    assert search_limit < jobs_limit


def test_all_limits_per_minute():
    """Test that all rate limits are specified per minute."""
    assert "/minute" in ANALYZE_RATE_LIMIT
    assert "/minute" in SEARCH_RATE_LIMIT
    assert "/minute" in JOBS_RATE_LIMIT


def test_rate_limit_error_includes_error_code():
    """Test that error response includes structured error code."""
    mock_request = MagicMock(spec=Request)
    mock_exc = MagicMock(spec=RateLimitExceeded)
    mock_exc.detail = "5 per 1 minute"

    response = rate_limit_error_handler(mock_request, mock_exc)

    response_content = response.body.decode()
    assert "error" in response_content
    assert "rate_limit_exceeded" in response_content


def test_limiter_key_function_configured():
    """Test that limiter is configured and instantiated."""
    # Limiter should be a valid slowapi Limiter instance
    assert limiter is not None
    from slowapi.extension import Limiter as SlowAPILimiter
    assert isinstance(limiter, SlowAPILimiter)


def test_rate_limit_decorators_applicable():
    """Test that rate limit decorators can be applied to endpoints."""
    # This is a meta-test: verify the decorator syntax is valid
    # by checking that the strings are valid rate limit specs

    def mock_endpoint_decorator(limit_string: str):
        """Mock endpoint with rate limit decorator."""
        # Valid rate limit strings should parse correctly
        parts = limit_string.split("/")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1] == "minute"
        return True

    # All limits should be valid
    assert mock_endpoint_decorator(ANALYZE_RATE_LIMIT)
    assert mock_endpoint_decorator(SEARCH_RATE_LIMIT)
    assert mock_endpoint_decorator(JOBS_RATE_LIMIT)


def test_429_status_code_standard():
    """Test that rate limit uses HTTP 429 (standard status code)."""
    assert status.HTTP_429_TOO_MANY_REQUESTS == 429


def test_rate_limit_error_does_not_expose_ips():
    """Test that rate limit error doesn't leak IP addresses in detail."""
    # Security: don't expose client IP in error message
    mock_request = MagicMock(spec=Request)
    mock_exc = MagicMock(spec=RateLimitExceeded)
    mock_exc.detail = "5 per 1 minute"

    response = rate_limit_error_handler(mock_request, mock_exc)

    response_content = response.body.decode()
    # Ensure no raw IP addresses in response (very basic check)
    assert "192.168" not in response_content  # Private IP range
    assert "10.0.0" not in response_content   # Private IP range


def test_rate_limits_configured_symmetrically():
    """Test that all protected endpoints have consistent rate limit configuration."""
    # All three endpoints should have configured limits
    limits = [ANALYZE_RATE_LIMIT, SEARCH_RATE_LIMIT, JOBS_RATE_LIMIT]
    
    for limit in limits:
        # Each should be a string like "N/minute"
        assert isinstance(limit, str)
        parts = limit.split("/")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert int(parts[0]) > 0
        assert parts[1] == "minute"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
