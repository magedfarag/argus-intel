"""FastAPI dependency injection helpers.

All singletons (settings, provider registry, cache, circuit breaker) are
constructed once at application startup in main.py and accessed via these
callables.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyCookie, APIKeyHeader, APIKeyQuery

from app.cache.client import CacheClient
from app.config import AppSettings, get_settings
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from app.services.job_manager import JobManager

# These are set by main.py lifespan
_registry:    Optional[ProviderRegistry] = None
_cache:       Optional[CacheClient]      = None
_breaker:     Optional[CircuitBreaker]   = None
_job_manager: Optional[JobManager]       = None


def set_registry(r: ProviderRegistry) -> None:
    global _registry
    _registry = r


def set_cache(c: CacheClient) -> None:
    global _cache
    _cache = c


def set_breaker(b: CircuitBreaker) -> None:
    global _breaker
    _breaker = b


def set_job_manager(jm: Optional[JobManager]) -> None:
    global _job_manager
    _job_manager = jm


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


def get_job_manager() -> Optional[JobManager]:
    return _job_manager


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


# ──────────────────────────────────────────────────────────────────────────────
# Role-Based Access Control (RBAC) — Phase 6 Track A
# ──────────────────────────────────────────────────────────────────────────────
# Token format (self-contained, no external IdP):
#   base64url(JSON payload).base64url(HMAC-SHA256 signature)
#
# JWT_SECRET (config) is used as the signing key; falls back to API_KEY.
# Three role tiers: analyst (1) < operator (2) < admin (3).
# In demo mode OR when no API_KEY is configured, role checks are bypassed.
# ──────────────────────────────────────────────────────────────────────────────


class UserRole(str, Enum):
    """Platform role tiers."""

    ANALYST = "analyst"
    OPERATOR = "operator"
    ADMIN = "admin"


_ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.ANALYST: 1,
    UserRole.OPERATOR: 2,
    UserRole.ADMIN: 3,
}


@dataclass(frozen=True)
class UserClaims:
    """Resolved identity and role for the current request."""

    user_id: str
    role: UserRole


# ── Token helpers ─────────────────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_access_token(user_id: str, role: UserRole) -> str:
    """Create a signed HMAC-SHA256 role token for the given user and role.

    The token is a dot-separated pair:
      base64url(payload_json).base64url(hmac_sha256_sig)

    Use the returned string as a Bearer token in the Authorization header.
    """
    settings = get_settings()
    secret = (settings.jwt_secret or settings.api_key).encode()
    payload_bytes = json.dumps(
        {"sub": user_id, "role": role.value}, separators=(",", ":")
    ).encode()
    payload_b64 = _b64url_encode(payload_bytes)
    sig = hmac.new(secret, payload_b64.encode(), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def _decode_role_token(token: str, settings) -> UserClaims | None:
    """Decode and verify a signed role token.  Returns None on any failure."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload_b64, sig_b64 = parts
    try:
        secret = (settings.jwt_secret or settings.api_key).encode()
        expected_sig = _b64url_decode(sig_b64)
        computed_sig = hmac.new(
            secret, payload_b64.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_sig, computed_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        role = UserRole(payload["role"])
        user_id = str(payload.get("sub", ""))
        return UserClaims(user_id=user_id, role=role)
    except Exception:  # noqa: BLE001
        return None


def _claims_from_raw_key(key: str, settings) -> UserClaims | None:
    """Return UserClaims for a raw API key, checking tiered keys first."""
    if settings.admin_api_key and key == settings.admin_api_key:
        return UserClaims(user_id="api-key-admin", role=UserRole.ADMIN)
    if settings.operator_api_key and key == settings.operator_api_key:
        return UserClaims(user_id="api-key-operator", role=UserRole.OPERATOR)
    if settings.analyst_api_key and key == settings.analyst_api_key:
        return UserClaims(user_id="api-key-analyst", role=UserRole.ANALYST)
    # Generic api_key → analyst role (backward compat)
    if settings.api_key and key == settings.api_key:
        return UserClaims(user_id="api-key-user", role=UserRole.ANALYST)
    return None


# ── Core dependency ───────────────────────────────────────────────────────────


def get_current_user(
    request: Request,
    header_key: str | None = Security(_api_key_header),
    query_key: str | None = Security(_api_key_query),
    cookie_key: str | None = Security(_api_key_cookie),
) -> UserClaims:
    """Resolve the calling user's identity and role.

    Resolution order:
    1. APP_MODE == "demo"       → admin bypass (demo behaviour preserved)
    2. No API_KEY configured    → admin bypass (insecure dev mode)
    3. Signed role token        → extract role from HMAC-verified claims
    4. Tiered raw API key       → derive role from key tier
    5. Generic api_key match    → analyst role (backward compat)
    6. No valid credential      → 401 Unauthorized
    """
    settings = get_settings()

    # Bypass in demo mode
    if settings.app_mode.value == "demo":
        claims = UserClaims(user_id="demo-user", role=UserRole.ADMIN)
        request.state.current_user_id = claims.user_id
        return claims

    # Insecure dev mode (no key configured)
    if not settings.api_key:
        claims = UserClaims(user_id="dev-user", role=UserRole.ADMIN)
        request.state.current_user_id = claims.user_id
        return claims

    # Extract raw token from whichever source was provided
    provided: str | None = None
    if header_key:
        provided = header_key[7:] if header_key.startswith("Bearer ") else header_key
    elif query_key:
        provided = query_key
    elif cookie_key:
        provided = cookie_key

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication required. "
                "Provide a Bearer token, ?api_key query param, or api_key cookie."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try signed role token first
    claims = _decode_role_token(provided, settings)
    if claims is None:
        # Fallback: raw API key tiered lookup
        claims = _claims_from_raw_key(provided, settings)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Make user_id available to the audit middleware via request.state
    request.state.current_user_id = claims.user_id
    return claims


# ── Role-check callables (use as Depends(require_operator)) ──────────────────


class _RoleChecker:
    """Callable dependency that enforces a minimum role level."""

    __slots__ = ("min_role",)

    def __init__(self, min_role: UserRole) -> None:
        self.min_role = min_role

    def __call__(
        self, user: UserClaims = Depends(get_current_user)
    ) -> UserClaims:
        if _ROLE_HIERARCHY[user.role] < _ROLE_HIERARCHY[self.min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"{self.min_role.value.capitalize()} role required. "
                    f"Current role: {user.role.value}"
                ),
            )
        return user


require_analyst: _RoleChecker = _RoleChecker(UserRole.ANALYST)
require_operator: _RoleChecker = _RoleChecker(UserRole.OPERATOR)
require_admin: _RoleChecker = _RoleChecker(UserRole.ADMIN)
