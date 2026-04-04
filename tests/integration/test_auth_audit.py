"""Integration tests for auth RBAC and audit logging — Phase 6 Track A.

Tests cover:
- require_analyst() blocks unauthenticated requests with 401
- require_operator() blocks analyst-role tokens with 403
- Demo mode bypasses role checks on all methods
- Audit log entries are created for instrumented endpoints
- Audit log events contain required fields
"""
from __future__ import annotations

import json
import logging
import os
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.audit_log import _audit_logger, _write_audit
from app.cache.client import CacheClient
from app.config import AppMode
from app.dependencies import UserRole, create_access_token
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from src.services.investigation_service import get_default_investigation_store
from src.services.absence_analytics import get_default_absence_service

# ── Shared payload helpers ────────────────────────────────────────────────────


def _absence_signal_payload(entity_id: str = "MV-TEST") -> dict:
    """Minimal valid AbsenceSignalCreateRequest payload."""
    return {
        "entity_id": entity_id,
        "signal_type": "ais_gap",
        "gap_start": "2026-04-01T00:00:00Z",
        "severity": "medium",
        "confidence": 0.75,
        "detection_method": "automated",
        "provenance": {"source": "test"},
    }


# ── Shared wiring ─────────────────────────────────────────────────────────────


def _wire_deps() -> None:
    reg = ProviderRegistry()
    reg.register(DemoProvider())
    dependencies.set_registry(reg)
    dependencies.set_cache(CacheClient())
    dependencies.set_breaker(CircuitBreaker())


def _reset_cfg() -> None:
    import app.config as _cfg

    _cfg._settings = None


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client_secured(monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient with API_KEY='sec-key', JWT_SECRET='sec-key', staging mode."""
    monkeypatch.setenv("API_KEY", "sec-key")
    monkeypatch.setenv("JWT_SECRET", "sec-key")
    monkeypatch.setenv("APP_MODE", "staging")
    _reset_cfg()
    _wire_deps()
    from app.main import app
    from app.resilience.rate_limiter import limiter

    limiter.reset()
    client = TestClient(app, raise_server_exceptions=False)
    get_default_investigation_store().clear()
    yield client
    get_default_investigation_store().clear()


@pytest.fixture()
def client_demo(monkeypatch) -> Generator[TestClient, None, None]:
    """TestClient in demo mode — all auth bypassed."""
    monkeypatch.setenv("API_KEY", "demo-key")
    monkeypatch.setenv("APP_MODE", "demo")
    _reset_cfg()
    _wire_deps()
    from app.main import app
    from app.resilience.rate_limiter import limiter

    limiter.reset()
    client = TestClient(app, raise_server_exceptions=False)
    get_default_investigation_store().clear()
    yield client
    get_default_investigation_store().clear()


@pytest.fixture()
def analyst_token(monkeypatch) -> str:
    """Signed analyst-role token."""
    monkeypatch.setenv("API_KEY", "sec-key")
    monkeypatch.setenv("JWT_SECRET", "sec-key")
    monkeypatch.setenv("APP_MODE", "staging")
    _reset_cfg()
    return create_access_token("analyst-user", UserRole.ANALYST)


@pytest.fixture()
def operator_token(monkeypatch) -> str:
    """Signed operator-role token."""
    monkeypatch.setenv("API_KEY", "sec-key")
    monkeypatch.setenv("JWT_SECRET", "sec-key")
    monkeypatch.setenv("APP_MODE", "staging")
    _reset_cfg()
    return create_access_token("op-user", UserRole.OPERATOR)


# ── 1. Unauthenticated access is blocked (401) ────────────────────────────────


class TestUnauthenticatedBlocked:
    def test_list_investigations_requires_auth(self, client_secured):
        r = client_secured.get("/api/v1/investigations")
        assert r.status_code == 401

    def test_create_investigation_requires_auth(self, client_secured):
        r = client_secured.post(
            "/api/v1/investigations", json={"name": "Test"}
        )
        assert r.status_code == 401

    def test_create_briefing_requires_auth(self, client_secured):
        r = client_secured.post(
            "/api/v1/analyst/briefings",
            json={
                "title": "Briefing",
                "sections": ["executive_summary"],
                "classification_label": "UNCLASSIFIED",
            },
        )
        assert r.status_code == 401

    def test_create_absence_signal_requires_auth(self, client_secured):
        r = client_secured.post(
            "/api/v1/absence/signals",
            json=_absence_signal_payload("MV-TEST"),
        )
        assert r.status_code == 401

    def test_attach_strike_evidence_requires_auth(self, client_secured):
        r = client_secured.post(
            "/api/v1/strikes/nonexistent/evidence",
            json={
                "evidence_id": "ev-1",
                "source_type": "imagery",
                "url": "https://example.com/img.tif",
                "description": "test",
            },
        )
        assert r.status_code == 401


# ── 2. Analyst role blocked from operator endpoints ───────────────────────────


class TestAnalystBlockedFromOperatorEndpoints:
    def test_create_investigation_needs_operator(
        self, client_secured, analyst_token
    ):
        r = client_secured.post(
            "/api/v1/investigations",
            json={"name": "Op Nightwatch"},
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert r.status_code == 403

    def test_delete_investigation_needs_operator(
        self, client_secured, operator_token, analyst_token
    ):
        # First create an investigation as operator
        create_r = client_secured.post(
            "/api/v1/investigations",
            json={"name": "Delete Me"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert create_r.status_code == 201
        inv_id = create_r.json()["id"]

        # Analyst tries to delete → 403
        del_r = client_secured.delete(
            f"/api/v1/investigations/{inv_id}",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert del_r.status_code == 403

    def test_update_investigation_needs_operator(
        self, client_secured, operator_token, analyst_token
    ):
        create_r = client_secured.post(
            "/api/v1/investigations",
            json={"name": "Op Alpha"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        inv_id = create_r.json()["id"]

        upd_r = client_secured.put(
            f"/api/v1/investigations/{inv_id}",
            json={"description": "updated"},
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert upd_r.status_code == 403

    def test_create_briefing_needs_operator(
        self, client_secured, analyst_token
    ):
        r = client_secured.post(
            "/api/v1/analyst/briefings",
            json={
                "title": "New Brief",
                "sections": ["executive_summary"],
                "classification_label": "UNCLASSIFIED",
            },
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert r.status_code == 403

    def test_create_absence_signal_needs_operator(
        self, client_secured, analyst_token
    ):
        r = client_secured.post(
            "/api/v1/absence/signals",
            json=_absence_signal_payload("MV-TEST"),
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert r.status_code == 403


# ── 3. Operator or higher can reach all mutation endpoints ────────────────────


class TestOperatorCanMutate:
    def test_operator_can_create_investigation(
        self, client_secured, operator_token
    ):
        r = client_secured.post(
            "/api/v1/investigations",
            json={"name": "Operator Creates"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert r.status_code == 201

    def test_operator_can_update_investigation(
        self, client_secured, operator_token
    ):
        cr = client_secured.post(
            "/api/v1/investigations",
            json={"name": "Update Test"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        inv_id = cr.json()["id"]
        ur = client_secured.put(
            f"/api/v1/investigations/{inv_id}",
            json={"description": "Updated"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert ur.status_code == 200

    def test_analyst_can_read_investigations(
        self, client_secured, analyst_token
    ):
        r = client_secured.get(
            "/api/v1/investigations",
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert r.status_code == 200


# ── 4. Demo mode bypasses ALL role checks ────────────────────────────────────


class TestDemoModeBypass:
    def test_demo_no_token_can_list_investigations(self, client_demo):
        r = client_demo.get("/api/v1/investigations")
        assert r.status_code == 200

    def test_demo_no_token_can_create_investigation(self, client_demo):
        r = client_demo.post(
            "/api/v1/investigations",
            json={"name": "Demo Create"},
        )
        assert r.status_code == 201

    def test_demo_no_token_can_create_briefing(self, client_demo):
        r = client_demo.post(
            "/api/v1/analyst/briefings",
            json={
                "title": "Demo Brief",
                "sections": ["executive_summary"],
                "classification_label": "UNCLASSIFIED",
            },
        )
        assert r.status_code == 201

    def test_demo_no_token_can_create_absence_signal(self, client_demo):
        r = client_demo.post(
            "/api/v1/absence/signals",
            json=_absence_signal_payload("MV-DEMO"),
        )
        assert r.status_code == 201


# ── 5. Audit log — field presence and event creation ─────────────────────────


class TestAuditLogFields:
    """Verify that _write_audit emits records with all required fields."""

    def test_required_fields_present(self, caplog):
        with caplog.at_level(logging.INFO, logger="argus.audit"):
            _write_audit(
                action="POST /api/v1/investigations",
                user_id="test-user-id",
                resource_type="investigation",
                resource_id="/api/v1/investigations/abc",
                ip_address="10.0.0.1",
                result="success",
            )

        records = [r for r in caplog.records if r.name == "argus.audit"]
        assert len(records) >= 1
        payload = json.loads(records[0].getMessage())
        for field in ("action", "user_id", "resource_type", "resource_id", "timestamp", "ip_address", "result"):
            assert field in payload, f"Missing field: {field}"

    def test_user_id_is_hashed(self, caplog):
        with caplog.at_level(logging.INFO, logger="argus.audit"):
            _write_audit(
                action="DELETE /api/v1/investigations/x",
                user_id="cleartext-id",
                resource_type="investigation",
                resource_id="/api/v1/investigations/x",
                ip_address="127.0.0.1",
                result="success",
            )
        records = [r for r in caplog.records if r.name == "argus.audit"]
        payload = json.loads(records[0].getMessage())
        # User ID should not contain the cleartext identity
        assert "cleartext-id" not in payload["user_id"]
        # Should be a 16-char hex string
        assert len(payload["user_id"]) == 16

    def test_timestamp_is_iso8601(self, caplog):
        import re

        with caplog.at_level(logging.INFO, logger="argus.audit"):
            _write_audit(
                action="PUT /api/v1/investigations/y",
                user_id="user-y",
                resource_type="investigation",
                resource_id="/api/v1/investigations/y",
                ip_address="192.168.1.1",
                result="denied",
            )
        records = [r for r in caplog.records if r.name == "argus.audit"]
        payload = json.loads(records[0].getMessage())
        # ISO 8601 with timezone: 2026-04-04T12:00:00+00:00
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", payload["timestamp"])

    def test_result_can_be_denied(self, caplog):
        with caplog.at_level(logging.INFO, logger="argus.audit"):
            _write_audit(
                action="POST /api/v1/absence/signals",
                user_id="blocked-user",
                resource_type="absence",
                resource_id="/api/v1/absence/signals",
                ip_address="10.1.1.1",
                result="denied",
            )
        records = [r for r in caplog.records if r.name == "argus.audit"]
        payload = json.loads(records[0].getMessage())
        assert payload["result"] == "denied"


# ── 6. Audit middleware invoked on instrumented endpoints ────────────────────


class TestAuditMiddlewareIntegration:
    """Verify the middleware records events when an instrumented path is called.

    We test via the _write_audit function (patched) so we don't depend on
    logger handler configuration in the test environment.
    """

    def test_create_investigation_emits_audit_event(
        self, client_demo, caplog
    ):
        with caplog.at_level(logging.INFO, logger="argus.audit"):
            client_demo.post(
                "/api/v1/investigations",
                json={"name": "Audit Test Inv"},
            )
        # Give background task a chance to run (TestClient is sync)
        audit_records = [r for r in caplog.records if r.name == "argus.audit"]
        assert len(audit_records) >= 1
        payload = json.loads(audit_records[0].getMessage())
        assert "investigations" in payload["action"]

    def test_delete_investigation_emits_audit_event(
        self, client_demo, caplog
    ):
        # Create first
        cr = client_demo.post(
            "/api/v1/investigations", json={"name": "To Delete"}
        )
        inv_id = cr.json()["id"]

        with caplog.at_level(logging.INFO, logger="argus.audit"):
            client_demo.delete(f"/api/v1/investigations/{inv_id}")

        audit_records = [r for r in caplog.records if r.name == "argus.audit"]
        assert len(audit_records) >= 1
        actions = [json.loads(r.getMessage()).get("action", "") for r in audit_records]
        assert any("investigations" in a for a in actions)

    def test_create_absence_signal_emits_audit_event(
        self, client_demo, caplog
    ):
        with caplog.at_level(logging.INFO, logger="argus.audit"):
            client_demo.post(
                "/api/v1/absence/signals",
                json=_absence_signal_payload("MV-AUDIT"),
            )
        audit_records = [r for r in caplog.records if r.name == "argus.audit"]
        assert len(audit_records) >= 1
        payload = json.loads(audit_records[0].getMessage())
        assert "absence" in payload["action"]
