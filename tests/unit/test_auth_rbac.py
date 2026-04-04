"""Unit tests for RBAC — Phase 6 Track A.

Tests cover:
- UserRole enum values and hierarchy
- create_access_token / _decode_role_token roundtrip
- Tampered/invalid token rejection
- _claims_from_raw_key tiered lookup
- get_current_user bypass modes (demo, dev)
- _RoleChecker enforcement (require_analyst, require_operator, require_admin)
- Token with wrong secret is rejected
"""
from __future__ import annotations

import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies import (
    UserClaims,
    UserRole,
    _RoleChecker,
    _ROLE_HIERARCHY,
    _claims_from_raw_key,
    _decode_role_token,
    create_access_token,
    require_analyst,
    require_operator,
    require_admin,
    get_current_user,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset the settings singleton between tests so env patches take effect."""
    import app.config as _cfg

    orig = _cfg._settings
    _cfg._settings = None
    yield
    _cfg._settings = orig


@pytest.fixture()
def settings_with_key(monkeypatch):
    """AppSettings with API_KEY='test-key', jwt_secret='test-secret'."""
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("APP_MODE", "staging")
    import app.config as _cfg

    _cfg._settings = None
    from app.config import get_settings

    return get_settings()


@pytest.fixture()
def settings_demo(monkeypatch):
    """AppSettings in demo mode."""
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("APP_MODE", "demo")
    import app.config as _cfg

    _cfg._settings = None
    from app.config import get_settings

    return get_settings()


@pytest.fixture()
def settings_no_key(monkeypatch):
    """AppSettings with no API_KEY (insecure dev mode)."""
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("APP_MODE", "staging")
    import app.config as _cfg

    _cfg._settings = None
    from app.config import get_settings

    return get_settings()


# ── 1. UserRole hierarchy ─────────────────────────────────────────────────────


class TestUserRoleHierarchy:
    def test_analyst_is_lowest(self):
        assert _ROLE_HIERARCHY[UserRole.ANALYST] == 1

    def test_operator_middle(self):
        assert _ROLE_HIERARCHY[UserRole.OPERATOR] == 2

    def test_admin_is_highest(self):
        assert _ROLE_HIERARCHY[UserRole.ADMIN] == 3

    def test_admin_outranks_operator(self):
        assert _ROLE_HIERARCHY[UserRole.ADMIN] > _ROLE_HIERARCHY[UserRole.OPERATOR]

    def test_operator_outranks_analyst(self):
        assert _ROLE_HIERARCHY[UserRole.OPERATOR] > _ROLE_HIERARCHY[UserRole.ANALYST]

    def test_role_enum_values(self):
        assert UserRole.ANALYST.value == "analyst"
        assert UserRole.OPERATOR.value == "operator"
        assert UserRole.ADMIN.value == "admin"


# ── 2. Token create / decode ──────────────────────────────────────────────────


class TestTokenRoundtrip:
    def test_analyst_token_roundtrips(self, settings_with_key):
        token = create_access_token("alice", UserRole.ANALYST)
        claims = _decode_role_token(token, settings_with_key)
        assert claims is not None
        assert claims.user_id == "alice"
        assert claims.role == UserRole.ANALYST

    def test_operator_token_roundtrips(self, settings_with_key):
        token = create_access_token("bob", UserRole.OPERATOR)
        claims = _decode_role_token(token, settings_with_key)
        assert claims is not None
        assert claims.role == UserRole.OPERATOR

    def test_admin_token_roundtrips(self, settings_with_key):
        token = create_access_token("sre", UserRole.ADMIN)
        claims = _decode_role_token(token, settings_with_key)
        assert claims is not None
        assert claims.role == UserRole.ADMIN

    def test_tampered_payload_rejected(self, settings_with_key):
        token = create_access_token("alice", UserRole.ANALYST)
        # Flip a character in the payload part to simulate tampering
        parts = token.split(".")
        corrupted = parts[0][:-1] + ("a" if parts[0][-1] != "a" else "b")
        tampered = f"{corrupted}.{parts[1]}"
        assert _decode_role_token(tampered, settings_with_key) is None

    def test_tampered_signature_rejected(self, settings_with_key):
        token = create_access_token("alice", UserRole.ANALYST)
        parts = token.split(".")
        bad_sig = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        tampered = f"{parts[0]}.{bad_sig}"
        assert _decode_role_token(tampered, settings_with_key) is None

    def test_wrong_secret_rejected(self, monkeypatch):
        """Token signed with one secret is rejected when secret changes."""
        monkeypatch.setenv("API_KEY", "secret-a")
        monkeypatch.setenv("JWT_SECRET", "secret-a")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None
        settings_a = _cfg.get_settings()

        token = create_access_token("alice", UserRole.OPERATOR)

        monkeypatch.setenv("JWT_SECRET", "secret-b")
        _cfg._settings = None
        settings_b = _cfg.get_settings()

        # Token was signed with secret-a; settings_b uses secret-b → reject
        assert _decode_role_token(token, settings_b) is None

    def test_empty_string_is_not_valid_token(self, settings_with_key):
        assert _decode_role_token("", settings_with_key) is None

    def test_random_junk_is_not_valid_token(self, settings_with_key):
        assert _decode_role_token("not.a.real.token.at.all", settings_with_key) is None


# ── 3. Tiered API key lookup ──────────────────────────────────────────────────


class TestTieredApiKeys:
    def test_admin_key_returns_admin_role(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "generic")
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None
        settings = _cfg.get_settings()
        claims = _claims_from_raw_key("admin-secret", settings)
        assert claims is not None
        assert claims.role == UserRole.ADMIN

    def test_operator_key_returns_operator_role(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "generic")
        monkeypatch.setenv("OPERATOR_API_KEY", "op-secret")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None
        settings = _cfg.get_settings()
        claims = _claims_from_raw_key("op-secret", settings)
        assert claims is not None
        assert claims.role == UserRole.OPERATOR

    def test_generic_api_key_returns_analyst_role(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "generic-key")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None
        settings = _cfg.get_settings()
        claims = _claims_from_raw_key("generic-key", settings)
        assert claims is not None
        assert claims.role == UserRole.ANALYST

    def test_unknown_key_returns_none(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "generic-key")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None
        settings = _cfg.get_settings()
        claims = _claims_from_raw_key("wrong-key", settings)
        assert claims is None

    def test_admin_key_priority_over_generic(self, monkeypatch):
        """If admin_api_key == api_key (misconfiguration), admin wins."""
        monkeypatch.setenv("API_KEY", "shared-key")
        monkeypatch.setenv("ADMIN_API_KEY", "shared-key")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None
        settings = _cfg.get_settings()
        claims = _claims_from_raw_key("shared-key", settings)
        assert claims is not None
        assert claims.role == UserRole.ADMIN


# ── 4. Role checker enforcement ───────────────────────────────────────────────


class TestRoleChecker:
    """Test _RoleChecker via a minimal FastAPI app."""

    @staticmethod
    def _make_app(checker: _RoleChecker) -> FastAPI:
        mini = FastAPI()

        @mini.get("/protected")
        def _route(user: UserClaims = Depends(checker)):
            return {"role": user.role.value}

        return mini

    def test_analyst_checker_passes_analyst(self):
        """analyst role should pass the analyst checker."""
        app = self._make_app(require_analyst)
        client = TestClient(app)
        with client:
            # No API_KEY configured → dev bypass (admin role)
            r = client.get("/protected")
        assert r.status_code == 200

    def test_operator_checker_blocks_analyst_token(self, monkeypatch):
        """operator checker should reject a valid analyst-role token."""
        monkeypatch.setenv("API_KEY", "secret")
        monkeypatch.setenv("JWT_SECRET", "secret")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None

        token = create_access_token("alice", UserRole.ANALYST)
        app_instance = self._make_app(require_operator)
        client = TestClient(app_instance, raise_server_exceptions=False)
        with client:
            r = client.get(
                "/protected", headers={"Authorization": f"Bearer {token}"}
            )
        assert r.status_code == 403

    def test_operator_checker_passes_operator_token(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        monkeypatch.setenv("JWT_SECRET", "secret")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None

        token = create_access_token("bob", UserRole.OPERATOR)
        app_instance = self._make_app(require_operator)
        client = TestClient(app_instance, raise_server_exceptions=False)
        with client:
            r = client.get(
                "/protected", headers={"Authorization": f"Bearer {token}"}
            )
        assert r.status_code == 200

    def test_admin_checker_blocks_operator_token(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        monkeypatch.setenv("JWT_SECRET", "secret")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None

        token = create_access_token("bob", UserRole.OPERATOR)
        app_instance = self._make_app(require_admin)
        client = TestClient(app_instance, raise_server_exceptions=False)
        with client:
            r = client.get(
                "/protected", headers={"Authorization": f"Bearer {token}"}
            )
        assert r.status_code == 403

    def test_no_token_returns_401(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        monkeypatch.setenv("JWT_SECRET", "secret")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None

        app_instance = self._make_app(require_analyst)
        client = TestClient(app_instance, raise_server_exceptions=False)
        with client:
            r = client.get("/protected")
        assert r.status_code == 401

    def test_demo_mode_bypasses_admin_checker(self, monkeypatch):
        """In demo mode every request is treated as admin regardless of token."""
        monkeypatch.setenv("API_KEY", "secret")
        monkeypatch.setenv("APP_MODE", "demo")
        import app.config as _cfg

        _cfg._settings = None

        app_instance = self._make_app(require_admin)
        client = TestClient(app_instance, raise_server_exceptions=False)
        with client:
            # No token at all — demo mode should bypass
            r = client.get("/protected")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_dev_mode_no_key_bypasses_operator_checker(self, monkeypatch):
        """When no API_KEY is configured, dev-mode bypass grants admin role."""
        monkeypatch.setenv("API_KEY", "")
        monkeypatch.setenv("APP_MODE", "staging")
        import app.config as _cfg

        _cfg._settings = None

        app_instance = self._make_app(require_operator)
        client = TestClient(app_instance, raise_server_exceptions=False)
        with client:
            r = client.get("/protected")
        assert r.status_code == 200


# ── 5. UserClaims immutability ────────────────────────────────────────────────


class TestUserClaimsImmutability:
    def test_frozen_dataclass_cannot_be_mutated(self):
        claims = UserClaims(user_id="alice", role=UserRole.ANALYST)
        with pytest.raises((AttributeError, TypeError)):
            claims.role = UserRole.ADMIN  # type: ignore[misc]

    def test_equality_by_value(self):
        c1 = UserClaims(user_id="alice", role=UserRole.ANALYST)
        c2 = UserClaims(user_id="alice", role=UserRole.ANALYST)
        assert c1 == c2

    def test_different_roles_not_equal(self):
        c1 = UserClaims(user_id="alice", role=UserRole.ANALYST)
        c2 = UserClaims(user_id="alice", role=UserRole.OPERATOR)
        assert c1 != c2
