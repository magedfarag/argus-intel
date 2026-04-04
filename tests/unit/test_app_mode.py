"""Unit tests for APP_MODE feature flag (P1-4)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.config import AppMode, AppSettings
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.providers.base import ProviderUnavailableError
from app.cache.client import CacheClient
from app.services.analysis import AnalysisService
from app import dependencies


class TestAppModeEnum:
    """Tests for AppMode enum definition and defaults."""

    def test_enum_has_three_values(self):
        assert set(AppMode) == {AppMode.DEMO, AppMode.STAGING, AppMode.PRODUCTION}

    def test_enum_string_values(self):
        assert AppMode.DEMO.value == "demo"
        assert AppMode.STAGING.value == "staging"
        assert AppMode.PRODUCTION.value == "production"

    def test_default_mode_is_staging(self):
        settings = AppSettings(redis_url="")
        assert settings.app_mode == AppMode.STAGING

    def test_mode_from_string_demo(self):
        settings = AppSettings(app_mode="demo", redis_url="")
        assert settings.app_mode == AppMode.DEMO

    def test_mode_from_string_production(self):
        settings = AppSettings(app_mode="production", redis_url="")
        assert settings.app_mode == AppMode.PRODUCTION


class TestProviderSelectionByMode:
    """Tests for ProviderRegistry.select_provider_by_mode()."""

    @pytest.fixture()
    def registry(self) -> ProviderRegistry:
        reg = ProviderRegistry()
        reg.register(DemoProvider())
        return reg

    def test_demo_mode_returns_demo_only(self, registry):
        providers, desc = registry.select_provider_by_mode(AppMode.DEMO)
        assert providers == ["demo"]
        assert "Demo" in desc

    def test_staging_mode_includes_fallback(self, registry):
        providers, desc = registry.select_provider_by_mode(AppMode.STAGING)
        assert "demo" in providers
        assert "sentinel2" in providers
        assert "Staging" in desc

    def test_production_mode_no_demo_fallback(self, registry):
        providers, desc = registry.select_provider_by_mode(AppMode.PRODUCTION)
        assert "demo" not in providers
        assert "sentinel2" in providers
        assert "Production" in desc


class TestResolveProviderByMode:
    """Tests for AnalysisService._resolve_provider() respecting app mode."""

    @pytest.fixture()
    def demo_registry(self) -> ProviderRegistry:
        reg = ProviderRegistry()
        reg.register(DemoProvider())
        return reg

    @pytest.fixture()
    def cache(self) -> CacheClient:
        return CacheClient(redis_url="", ttl_seconds=60, max_entries=64)

    def test_registry_respects_app_mode_demo(self, demo_registry, cache):
        """In DEMO mode, always returns demo provider regardless of request."""
        settings = AppSettings(app_mode="demo", redis_url="")
        svc = AnalysisService(registry=demo_registry, cache=cache, settings=settings)
        provider, is_demo, warnings = svc._resolve_provider("sentinel2")
        assert is_demo is True
        assert provider.provider_name == "demo"

    def test_registry_respects_app_mode_production(self, demo_registry, cache):
        """In PRODUCTION mode, raises error when no live provider is available."""
        settings = AppSettings(app_mode="production", redis_url="")
        svc = AnalysisService(registry=demo_registry, cache=cache, settings=settings)
        with pytest.raises(ProviderUnavailableError):
            svc._resolve_provider("sentinel2")

    def test_staging_mode_falls_back_to_demo(self, demo_registry, cache):
        """In STAGING mode, falls back to demo when live provider unavailable."""
        settings = AppSettings(app_mode="staging", redis_url="")
        svc = AnalysisService(registry=demo_registry, cache=cache, settings=settings)
        provider, is_demo, warnings = svc._resolve_provider("sentinel2")
        assert is_demo is True
        assert len(warnings) > 0


class TestSelectProviderByMode:
    """Tests for ProviderRegistry.select_provider() respecting mode parameter."""

    @pytest.fixture()
    def demo_only_registry(self) -> ProviderRegistry:
        reg = ProviderRegistry()
        reg.register(DemoProvider())
        return reg

    def test_auto_production_returns_none_when_only_demo(self, demo_only_registry):
        """In production mode, auto-resolution must not return demo."""
        result = demo_only_registry.select_provider("auto", mode=AppMode.PRODUCTION)
        assert result is None

    def test_auto_staging_returns_demo_fallback(self, demo_only_registry):
        """In staging mode, auto-resolution may return demo as last resort."""
        result = demo_only_registry.select_provider("auto", mode=AppMode.STAGING)
        assert result is not None
        assert result.provider_name == "demo"

    def test_auto_no_mode_returns_demo_fallback(self, demo_only_registry):
        """Without a mode restriction, auto-resolution returns demo."""
        result = demo_only_registry.select_provider("auto")
        assert result is not None
        assert result.provider_name == "demo"

    def test_explicit_demo_in_production_returns_none(self, demo_only_registry):
        """Explicitly requesting 'demo' in production mode returns None."""
        result = demo_only_registry.select_provider("demo", mode=AppMode.PRODUCTION)
        assert result is None

    def test_explicit_demo_in_staging_returns_demo(self, demo_only_registry):
        """Explicitly requesting 'demo' in staging mode returns the demo provider."""
        result = demo_only_registry.select_provider("demo", mode=AppMode.STAGING)
        assert result is not None
        assert result.provider_name == "demo"


POLYGON = {"type": "Polygon", "coordinates": [[[30.0, 50.0], [30.1, 50.0], [30.1, 50.1], [30.0, 50.1], [30.0, 50.0]]]}


class TestSearchEndpointFailFast:
    """Tests for POST /api/search fail-fast in production mode."""

    @pytest.fixture()
    def prod_client(self):
        """TestClient with demo-only registry in PRODUCTION mode."""
        import os
        from app.resilience.circuit_breaker import CircuitBreaker
        reg = ProviderRegistry()
        reg.register(DemoProvider())
        dependencies.set_registry(reg)
        dependencies.set_cache(CacheClient())
        dependencies.set_breaker(CircuitBreaker())
        old_mode = os.environ.get("APP_MODE", "staging")
        os.environ["APP_MODE"] = "production"
        import app.config as _cfg
        _cfg._settings = None
        from app.main import app
        from app.resilience.rate_limiter import limiter
        limiter.reset()
        client = TestClient(app, raise_server_exceptions=True)
        yield client
        os.environ["APP_MODE"] = old_mode
        _cfg._settings = None

    def test_search_production_no_live_provider_returns_503(self, prod_client):
        """Production mode: /api/search returns 503 when only demo is registered."""
        r = prod_client.post(
            "/api/search",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"},
        )
        assert r.status_code == 503
        assert "demo fallback is disabled" in r.json()["detail"].lower() or \
               "not available" in r.json()["detail"].lower()

    def test_search_staging_no_live_provider_returns_200_with_demo(self, demo_only_registry):
        """Staging mode: /api/search falls back to demo and returns 200."""
        from app.resilience.circuit_breaker import CircuitBreaker
        dependencies.set_registry(demo_only_registry)
        dependencies.set_cache(CacheClient())
        dependencies.set_breaker(CircuitBreaker())
        from app.main import app
        from app.resilience.rate_limiter import limiter
        limiter.reset()
        client = TestClient(app, raise_server_exceptions=True)
        r = client.post(
            "/api/search",
            json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28"},
        )
        assert r.status_code == 200
        assert "scenes" in r.json()

    @pytest.fixture()
    def demo_only_registry(self) -> ProviderRegistry:
        reg = ProviderRegistry()
        reg.register(DemoProvider())
        return reg
