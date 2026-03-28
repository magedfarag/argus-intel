"""FastAPI dependency injection helpers.

All singletons (settings, provider registry, cache, circuit breaker) are
constructed once at application startup in main.py and accessed via these
callables.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyCookie, APIKeyHeader, APIKeyQuery

from backend.app.cache.client import CacheClient
from backend.app.config import AppSettings, get_settings
from backend.app.providers.registry import ProviderRegistry
from backend.app.resilience.circuit_breaker import CircuitBreaker

# These are set by main.py lifespan
_registry: Optional[ProviderRegistry] = None
_cache:    Optional[CacheClient]      = None
_breaker:  Optional[CircuitBreaker]   = None


def set_registry(r: ProviderRegistry) -> None:
    global _registry
    _registry = r


def set_cache(c: CacheClient) -> None:
    global _cache
    _cache = c


def set_breaker(b: CircuitBreaker) -> None:
    global _breaker
    _breaker = b


# FastAPI-injectable callables ─────────────────────────────────────────────

def get_app_settings() -> AppSettings:
    return get_settings()


def get_registry() -> ProviderRegistry:
    assert _registry is not None, "ProviderRegistry not initialised"
    return _registry


def get_cache() -> CacheClient:
    assert _cache is not None, "CacheClient not initialised"
    return _cache


def get_circuit_breaker() -> CircuitBreaker:
    assert _breaker is not None, "CircuitBreaker not initialised"
    return _breaker


# ──────────────────────────────────────────────────────────────────────────
# API Key authentication — REQUIRED for all mutation endpoints
# ──────────────────────────────────────────────────────────────────────────
# Supports three methods (in priority order):
#   1. Authorization: Bearer <key> header
#   2. ?api_key=<key> query parameter (for WebSocket / browser testing)
#   3. api_key=<key> cookie (for SPAs)
#
# Set API_KEY in .env. If unset, authentication is skipped (insecure dev mode).
# For production, MUST set a strong API_KEY (e.g., openssl rand -hex 32).

_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
_api_key_query = APIKeyQuery(name="api_key", auto_error=False)
_api_key_cookie = APIKeyCookie(name="api_key", auto_error=False)


def verify_api_key(
    header_key: str | None = Security(_api_key_header),
    query_key: str | None = Security(_api_key_query),
    cookie_key: str | None = Security(_api_key_cookie),
) -> str:
    """
    Verify API key from one of three sources: Authorization header (Bearer),
    query parameter, or cookie. Raises HTTPException(403) if no valid key found.

    In secure mode (API_KEY env var set), one of these three MUST be provided
    and match. In insecure mode (API_KEY unset), skips validation.
    """
    settings = get_settings()
    configured_key = settings.api_key

    # Insecure dev mode: no API key configured
    if not configured_key:
        return "INSECURE_DEV_MODE"

    # Extract Bearer token from Authorization header (format: "Bearer <key>")
    provided_key = None
    if header_key:
        if header_key.startswith("Bearer "):
            provided_key = header_key[7:]  # Strip "Bearer " prefix
        else:
            provided_key = header_key
    elif query_key:
        provided_key = query_key
    elif cookie_key:
        provided_key = cookie_key

    if not provided_key or provided_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Provide via Authorization header (Bearer), ?api_key query param, or api_key cookie.",
        )

    return provided_key

    # Extract Bearer token from Authorization header (format: "Bearer <key>")
    provided_key = None
    if header_key:
        if header_key.startswith("Bearer "):
            provided_key = header_key[7:]  # Strip "Bearer " prefix
        else:
            provided_key = header_key
    elif query_key:
        provided_key = query_key
    elif cookie_key:
        provided_key = cookie_key

    if not provided_key or provided_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Provide via Authorization header (Bearer), ?api_key query param, or api_key cookie.",
        )

    return provided_key
