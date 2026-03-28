"""Unit tests for Sentinel-2 provider."""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
import httpx
from backend.app.config import AppSettings
from backend.app.providers.sentinel2 import Sentinel2Provider

@pytest.fixture
def sentinel2_settings():
    return AppSettings(
        app_mode="auto",
        redis_url="",
        sentinel2_client_id="test_id",
        sentinel2_client_secret="test_secret",
        http_timeout_seconds=10,
    )

class TestSentinel2OAuth2:
    def test_validate_credentials_success(self, sentinel2_settings):
        provider = Sentinel2Provider(sentinel2_settings)
        mock_resp = {"access_token": "token123", "expires_in": 3600}
        with patch("httpx.post") as m:
            m.return_value = MagicMock(json=lambda: mock_resp, raise_for_status=lambda: None)
            ok, msg = provider.validate_credentials()
            assert ok is True
            assert "OAuth2" in msg

    def test_validate_credentials_no_creds(self):
        """Test credential validation fails when credentials not set."""
        settings = AppSettings(
            app_mode="demo",
            redis_url="",
            sentinel2_client_id="",
            sentinel2_client_secret="",
        )
        provider = Sentinel2Provider(settings)
        ok, msg = provider.validate_credentials()
        assert ok is False
        assert "not set" in msg.lower()

    def test_get_token_caches(self, sentinel2_settings):
        """Test that _get_token caches the token and reuses it."""
        provider = Sentinel2Provider(sentinel2_settings)
        mock_resp = {"access_token": "token123", "expires_in": 3600}
        with patch("httpx.post") as m:
            m.return_value = MagicMock(json=lambda: mock_resp, raise_for_status=lambda: None)
            t1 = provider._get_token()
            assert t1 == "token123"
            assert m.call_count == 1
            
            t2 = provider._get_token()
            assert t2 == "token123"
            assert m.call_count == 1  # Still 1, token was cached


class TestSentinel2STAC:
    """Test suite for STAC scene search."""

    def test_search_imagery_success(self, sentinel2_settings):
        """Test successful STAC scene search."""
        provider = Sentinel2Provider(sentinel2_settings)
        
        token_resp = {"access_token": "token", "expires_in": 3600}
        stac_resp = {"features": [{
            "id": "S2A_123",
            "properties": {"datetime": "2026-03-28T00:00:00Z", "eo:cloud_cover": 15.0},
            "bbox": [-1.0, 51.4, -0.5, 51.8],
            "geometry": {"type": "Polygon", "coordinates": [[[-1.0, 51.4], [-0.5, 51.4], [-0.5, 51.8], [-1.0, 51.8], [-1.0, 51.4]]]},
            "assets": {"B04": {"href": "s3://b04.tif"}, "B08": {"href": "s3://b08.tif"}},
        }]}
        test_aoi = {"type": "Polygon", "coordinates": [[[-1.0, 51.4], [-0.5, 51.4], [-0.5, 51.8], [-1.0, 51.8], [-1.0, 51.4]]]}
        
        with patch("httpx.post") as m1, patch("httpx.get") as m2:
            m1.return_value = MagicMock(json=lambda: token_resp, raise_for_status=lambda: None)
            m2.return_value = MagicMock(json=lambda: stac_resp, raise_for_status=lambda: None)
            scenes = provider.search_imagery(test_aoi, "2026-02-26", "2026-03-28")
            
            assert len(scenes) == 1
            assert scenes[0].provider == "sentinel2"
            assert scenes[0].cloud_cover == 15.0

    def test_search_imagery_empty_results(self, sentinel2_settings):
        """Test search returning no scenes."""
        provider = Sentinel2Provider(sentinel2_settings)
        token_resp = {"access_token": "token", "expires_in": 3600}
        stac_resp = {"features": []}
        test_aoi = {"type": "Polygon", "coordinates": [[[-90.0, -60.0], [-89.0, -60.0], [-89.0, -59.0], [-90.0, -59.0], [-90.0, -60.0]]]}
        
        with patch("httpx.post") as m1, patch("httpx.get") as m2:
            m1.return_value = MagicMock(json=lambda: token_resp, raise_for_status=lambda: None)
            m2.return_value = MagicMock(json=lambda: stac_resp, raise_for_status=lambda: None)
            scenes = provider.search_imagery(test_aoi, "2026-02-26", "2026-03-28")
            
            assert scenes == []

class TestSentinel2Capabilities:
    """Test suite for provider capabilities."""

    def test_capabilities(self, sentinel2_settings):
        """Test that Sentinel-2 provider reports correct capabilities."""
        provider = Sentinel2Provider(sentinel2_settings)
        assert provider.resolution_m == 10
        assert provider.provider_name == "sentinel2"
        assert provider.display_name == "Sentinel-2 (Copernicus Data Space)"
        
        caps = provider.get_capabilities()
        assert caps.get("supports_cog_streaming") is True
        assert caps.get("requires_credentials") is True
        assert caps.get("collection") == "SENTINEL-2"


class TestSentinel2CircuitBreaker:
    """Test circuit breaker integration with Sentinel-2 provider."""

    def test_circuit_breaker_tracks_provider_state(self, sentinel2_settings):
        """Test that circuit breaker transitions are tracked per provider."""
        from backend.app.resilience.circuit_breaker import CircuitBreaker, CBState
        
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        # Initial state: CLOSED
        assert breaker.status("sentinel2") == CBState.CLOSED
        assert breaker.is_open("sentinel2") is False
        
        # Record 3 failures → should transition to OPEN
        for _ in range(3):
            breaker.record_failure("sentinel2")
        
        assert breaker.status("sentinel2") == CBState.OPEN
        assert breaker.is_open("sentinel2") is True
        
        # Record a success → should transition back to CLOSED
        breaker.record_success("sentinel2")
        assert breaker.status("sentinel2") == CBState.CLOSED
        assert breaker.is_open("sentinel2") is False

    def test_circuit_breaker_isolates_per_provider(self):
        """Test that circuit breaker state is isolated per provider."""
        from backend.app.resilience.circuit_breaker import CircuitBreaker, CBState
        
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        
        # Sentinel-2 fails
        breaker.record_failure("sentinel2")
        breaker.record_failure("sentinel2")
        assert breaker.status("sentinel2") == CBState.OPEN
        
        # Landsat should still be CLOSED
        assert breaker.status("landsat") == CBState.CLOSED
        assert breaker.is_open("landsat") is False
        
        # Landsat fails independently
        breaker.record_failure("landsat")
        assert breaker.status("landsat") == CBState.CLOSED  # needs 2 failures
        
        breaker.record_failure("landsat")
        assert breaker.status("landsat") == CBState.OPEN
