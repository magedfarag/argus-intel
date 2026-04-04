"""Unit tests for commercial provider stubs (P3-1): Maxar + Planet."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.config import AppSettings
from app.providers.base import ProviderUnavailableError
from app.providers.maxar import MaxarProvider
from app.providers.planet import PlanetProvider


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def settings_no_keys() -> AppSettings:
    return AppSettings(redis_url="", maxar_api_key="", planet_api_key="")


@pytest.fixture()
def settings_maxar() -> AppSettings:
    return AppSettings(redis_url="", maxar_api_key="test-maxar-key-123")


@pytest.fixture()
def settings_planet() -> AppSettings:
    return AppSettings(redis_url="", planet_api_key="test-planet-key-456")


# ── MaxarProvider ─────────────────────────────────────────────────────────

class TestMaxarProvider:
    def test_provider_name(self, settings_maxar):
        p = MaxarProvider(settings_maxar)
        assert p.provider_name == "maxar"
        assert p.display_name == "Maxar (SecureWatch)"

    def test_validate_credentials_no_key(self, settings_no_keys):
        p = MaxarProvider(settings_no_keys)
        ok, reason = p.validate_credentials()
        assert ok is False
        assert "MAXAR_API_KEY" in reason

    def test_validate_credentials_with_key(self, settings_maxar):
        p = MaxarProvider(settings_maxar)
        ok, reason = p.validate_credentials()
        assert ok is True
        assert "present" in reason.lower()

    def test_healthcheck_no_key(self, settings_no_keys):
        p = MaxarProvider(settings_no_keys)
        ok, reason = p.healthcheck()
        assert ok is False

    def test_search_imagery_no_key_raises(self, settings_no_keys):
        p = MaxarProvider(settings_no_keys)
        with pytest.raises(ProviderUnavailableError, match="MAXAR_API_KEY"):
            p.search_imagery(
                geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                start_date="2026-01-01",
                end_date="2026-03-01",
            )

    def test_fetch_scene_metadata_no_key(self, settings_no_keys):
        p = MaxarProvider(settings_no_keys)
        result = p.fetch_scene_metadata("some-scene-id")
        assert result is None

    def test_capabilities(self, settings_maxar):
        p = MaxarProvider(settings_maxar)
        caps = p.get_capabilities()
        assert caps["provider"] == "maxar"
        assert caps["supports_cog_streaming"] is True
        assert caps["requires_credentials"] is True
        assert caps["commercial"] is True
        assert caps["max_resolution_m"] == 0.3

    def test_search_imagery_with_key_calls_httpx(self, settings_maxar):
        p = MaxarProvider(settings_maxar)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"features": []}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            results = p.search_imagery(
                geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                start_date="2026-01-01",
                end_date="2026-03-01",
            )
            assert results == []
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "Bearer test-maxar-key-123" in str(call_kwargs)


# ── PlanetProvider ────────────────────────────────────────────────────────

class TestPlanetProvider:
    def test_provider_name(self, settings_planet):
        p = PlanetProvider(settings_planet)
        assert p.provider_name == "planet"
        assert p.display_name == "Planet (PlanetScope)"

    def test_validate_credentials_no_key(self, settings_no_keys):
        p = PlanetProvider(settings_no_keys)
        ok, reason = p.validate_credentials()
        assert ok is False
        assert "PLANET_API_KEY" in reason

    def test_validate_credentials_with_key(self, settings_planet):
        p = PlanetProvider(settings_planet)
        ok, reason = p.validate_credentials()
        assert ok is True

    def test_healthcheck_no_key(self, settings_no_keys):
        p = PlanetProvider(settings_no_keys)
        ok, reason = p.healthcheck()
        assert ok is False

    def test_search_imagery_no_key_raises(self, settings_no_keys):
        p = PlanetProvider(settings_no_keys)
        with pytest.raises(ProviderUnavailableError, match="PLANET_API_KEY"):
            p.search_imagery(
                geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                start_date="2026-01-01",
                end_date="2026-03-01",
            )

    def test_fetch_scene_metadata_no_key(self, settings_no_keys):
        p = PlanetProvider(settings_no_keys)
        result = p.fetch_scene_metadata("some-scene-id")
        assert result is None

    def test_capabilities(self, settings_planet):
        p = PlanetProvider(settings_planet)
        caps = p.get_capabilities()
        assert caps["provider"] == "planet"
        assert caps["requires_credentials"] is True
        assert caps["commercial"] is True
        assert caps["daily_revisit"] is True

    def test_search_imagery_with_key_calls_httpx(self, settings_planet):
        p = PlanetProvider(settings_planet)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"features": []}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            results = p.search_imagery(
                geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                start_date="2026-01-01",
                end_date="2026-03-01",
            )
            assert results == []
            mock_post.assert_called_once()


# ── Registry integration ──────────────────────────────────────────────────

class TestCommercialProviderRegistry:
    def test_maxar_registered_when_configured(self, settings_maxar):
        from app.providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        reg.register(MaxarProvider(settings_maxar))
        assert reg.get("maxar") is not None
        assert reg.is_available("maxar") is True

    def test_planet_registered_when_configured(self, settings_planet):
        from app.providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        reg.register(PlanetProvider(settings_planet))
        assert reg.get("planet") is not None
        assert reg.is_available("planet") is True

    def test_providers_unavailable_without_keys(self, settings_no_keys):
        from app.providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        reg.register(MaxarProvider(settings_no_keys))
        reg.register(PlanetProvider(settings_no_keys))
        assert reg.is_available("maxar") is False
        assert reg.is_available("planet") is False

    def test_mode_priority_includes_commercial(self):
        from app.config import AppMode
        from app.providers.registry import ProviderRegistry
        reg = ProviderRegistry()
        providers, _ = reg.select_provider_by_mode(AppMode.STAGING)
        assert "maxar" in providers
        assert "planet" in providers

    def test_config_exposes_commercial_keys(self):
        s = AppSettings(redis_url="", maxar_api_key="mk", planet_api_key="pk")
        assert s.maxar_is_configured() is True
        assert s.planet_is_configured() is True

    def test_config_not_configured_by_default(self):
        s = AppSettings(redis_url="")
        assert s.maxar_is_configured() is False
        assert s.planet_is_configured() is False