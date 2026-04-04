"""Shared pytest fixtures for all test suites."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

# Ensure tests run in isolated mode without external services
# Override any .env file settings so unit tests have deterministic defaults
os.environ["APP_MODE"] = "staging"
os.environ["REDIS_URL"] = ""
os.environ["CELERY_BROKER_URL"] = ""
os.environ["SENTINEL2_CLIENT_ID"] = ""
os.environ["SENTINEL2_CLIENT_SECRET"] = ""
os.environ["MAXAR_API_KEY"] = ""
os.environ["PLANET_API_KEY"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["API_KEY"] = ""  # Disable auth in tests unless explicitly patched

from app import dependencies
from app.cache.client import CacheClient
from app.config import AppSettings
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker

# Reset settings singleton so it picks up the overridden env vars above
import app.config as _cfg
_cfg._settings = None


@pytest.fixture(scope="session")
def demo_registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(DemoProvider())
    return reg


@pytest.fixture(scope="session")
def memory_cache() -> CacheClient:
    return CacheClient(redis_url="", ttl_seconds=60, max_entries=64)


@pytest.fixture(scope="session")
def circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, recovery_timeout=10)


@pytest.fixture(scope="session")
def app_client(demo_registry, memory_cache, circuit_breaker) -> TestClient:
    """Full TestClient with all singletons wired — reused for the whole session."""
    dependencies.set_registry(demo_registry)
    dependencies.set_cache(memory_cache)
    dependencies.set_breaker(circuit_breaker)
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="session")
def demo_settings() -> AppSettings:
    return AppSettings(app_mode="demo", redis_url="")


@pytest.fixture(autouse=True)
def _reset_query_cache():
    """Reset the in-process query cache singleton between every test.

    This prevents cached route responses from leaking across tests that
    mutate service singletons directly (e.g. absence_service.clear()).
    Without this fixture the session-scoped app_client shares one cache
    and cross-test isolation breaks.
    """
    from app.cache.query_cache import reset_query_cache
    reset_query_cache()
    yield
    reset_query_cache()


@pytest.fixture(scope="session")
def sentinel2_settings() -> AppSettings:
    """AppSettings with Sentinel-2 credentials configured for testing."""
    return AppSettings(
        app_mode="staging",
        redis_url="",
        sentinel2_client_id="test_client_id",
        sentinel2_client_secret="test_client_secret",
        sentinel2_token_url="https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        sentinel2_stac_url="https://catalogue.dataspace.copernicus.eu/stac",
        http_timeout_seconds=10,
    )
