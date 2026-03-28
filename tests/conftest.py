"""Shared pytest fixtures for all test suites."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

# Ensure tests run in isolated mode without external services
# Override any .env file settings
os.environ["REDIS_URL"] = ""
os.environ["CELERY_BROKER_URL"] = ""

from backend.app import dependencies
from backend.app.cache.client import CacheClient
from backend.app.config import AppSettings
from backend.app.providers.demo import DemoProvider
from backend.app.providers.registry import ProviderRegistry
from backend.app.resilience.circuit_breaker import CircuitBreaker


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
    from backend.app.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="session")
def demo_settings() -> AppSettings:
    return AppSettings(app_mode="demo", redis_url="")


@pytest.fixture(scope="session")
def sentinel2_settings() -> AppSettings:
    """AppSettings with Sentinel-2 credentials configured for testing."""
    return AppSettings(
        app_mode="auto",
        redis_url="",
        sentinel2_client_id="test_client_id",
        sentinel2_client_secret="test_client_secret",
        sentinel2_token_url="https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        sentinel2_stac_url="https://catalogue.dataspace.copernicus.eu/stac/v1",
        http_timeout_seconds=10,
    )
