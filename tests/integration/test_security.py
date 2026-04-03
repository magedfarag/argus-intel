"""Security tests for API authentication (P1-6) and CORS (P1-5)."""
from __future__ import annotations
import os
import pytest
from fastapi.testclient import TestClient
from app import dependencies
from app.cache.client import CacheClient
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker
from unittest.mock import patch

POLYGON = {"type": "Polygon", "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]}


@pytest.fixture
def client_with_auth():
    """Client configured with API_KEY authentication enabled."""
    reg = ProviderRegistry()
    reg.register(DemoProvider())
    dependencies.set_registry(reg)
    dependencies.set_cache(CacheClient())
    dependencies.set_breaker(CircuitBreaker())

    with patch.dict(os.environ, {"API_KEY": "test-secret-key"}):
        # Force reimport to pick up env var
        if 'app.config' in __import__('sys').modules:
            __import__('sys').modules['app.config']._settings = None
        from app.main import app
        from app.resilience.rate_limiter import limiter
        limiter.reset()
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def client_no_auth():
    """Client configured WITHOUT API_KEY authentication (insecure dev mode)."""
    reg = ProviderRegistry()
    reg.register(DemoProvider())
    dependencies.set_registry(reg)
    dependencies.set_cache(CacheClient())
    dependencies.set_breaker(CircuitBreaker())

    env_backup = os.environ.get("API_KEY")
    if "API_KEY" in os.environ:
        del os.environ["API_KEY"]

    try:
        if 'app.config' in __import__('sys').modules:
            __import__('sys').modules['app.config']._settings = None
        from app.main import app
        from app.resilience.rate_limiter import limiter
        limiter.reset()
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        if env_backup:
            os.environ["API_KEY"] = env_backup


class TestAPIKeyAuthentication:
    """Tests for API key authentication on protected endpoints."""

    def test_analyze_requires_auth_when_configured(self, client_with_auth):
        """POST /api/analyze without auth should return 403 when API_KEY is set."""
        response = client_with_auth.post(
            "/api/analyze",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"}
        )
        assert response.status_code == 403

    def test_analyze_auth_via_bearer_header(self, client_with_auth):
        """POST /api/analyze with Bearer token in Authorization header should succeed."""
        response = client_with_auth.post(
            "/api/analyze",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"},
            headers={"Authorization": "Bearer test-secret-key"}
        )
        assert response.status_code == 200
        assert response.json()["is_demo"] is True

    def test_analyze_auth_via_query_param(self, client_with_auth):
        """POST /api/analyze with ?api_key=<key> query param should succeed."""
        response = client_with_auth.post(
            "/api/analyze?api_key=test-secret-key",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"}
        )
        assert response.status_code == 200
        assert response.json()["is_demo"] is True

    def test_analyze_invalid_bearer_token(self, client_with_auth):
        """POST /api/analyze with wrong Bearer token should return 403."""
        response = client_with_auth.post(
            "/api/analyze",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"},
            headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 403

    def test_search_requires_auth_when_configured(self, client_with_auth):
        """POST /api/search without auth should return 403 when API_KEY is set."""
        response = client_with_auth.post(
            "/api/search",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"}
        )
        assert response.status_code == 403

    def test_search_auth_via_bearer_header(self, client_with_auth):
        """POST /api/search with Bearer token should succeed."""
        response = client_with_auth.post(
            "/api/search",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"},
            headers={"Authorization": "Bearer test-secret-key"}
        )
        assert response.status_code == 200
        assert "scenes" in response.json()

    def test_jobs_cancel_requires_auth_when_configured(self, client_with_auth):
        """DELETE /api/jobs/{id}/cancel without auth should return 403."""
        response = client_with_auth.delete("/api/jobs/test-job-id/cancel")
        assert response.status_code == 403

    def test_jobs_cancel_auth_via_bearer_header(self, client_with_auth):
        """DELETE /api/jobs/{id}/cancel with Bearer token should pass auth."""
        response = client_with_auth.delete(
            "/api/jobs/test-job-id/cancel",
            headers={"Authorization": "Bearer test-secret-key"}
        )
        assert response.status_code in [503, 404]

    def test_health_public_no_auth_required(self, client_with_auth):
        """GET /api/health should work without authentication."""
        response = client_with_auth.get("/api/health")
        assert response.status_code == 200

    def test_config_public_no_auth_required(self, client_with_auth):
        """GET /api/config should work without authentication."""
        response = client_with_auth.get("/api/config")
        assert response.status_code == 200

    def test_providers_public_no_auth_required(self, client_with_auth):
        """GET /api/providers should work without authentication."""
        response = client_with_auth.get("/api/providers")
        assert response.status_code == 200

    def test_credits_public_no_auth_required(self, client_with_auth):
        """GET /api/credits should work without authentication."""
        response = client_with_auth.get("/api/credits")
        assert response.status_code == 200

    def test_analyze_no_auth_required_in_dev_mode(self, client_no_auth):
        """POST /api/analyze should work without auth in insecure dev mode."""
        response = client_no_auth.post(
            "/api/analyze",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"}
        )
        assert response.status_code == 200
        assert response.json()["is_demo"] is True

    def test_search_no_auth_required_in_dev_mode(self, client_no_auth):
        """POST /api/search should work without auth in insecure dev mode."""
        response = client_no_auth.post(
            "/api/search",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"}
        )
        assert response.status_code == 200

    def test_jobs_cancel_no_auth_required_in_dev_mode(self, client_no_auth):
        """DELETE /api/jobs/{id}/cancel should work without auth in insecure dev mode."""
        response = client_no_auth.delete("/api/jobs/test-job-id/cancel")
        assert response.status_code in [503, 404]

    def test_bearer_token_without_prefix(self, client_with_auth):
        """Authorization header with wrong key should fail."""
        response = client_with_auth.post(
            "/api/analyze",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"},
            headers={"Authorization": "wrong-key-value"}
        )
        assert response.status_code == 403

    def test_empty_api_key_query_param(self, client_with_auth):
        """Empty ?api_key= query param should fail authentication."""
        response = client_with_auth.post(
            "/api/analyze?api_key=",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"}
        )
        assert response.status_code == 403
