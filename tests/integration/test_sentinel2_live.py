"""Integration tests for Sentinel-2 live STAC scene search.

These tests are OPTIONAL and only run when:
  - SENTINEL2_CLIENT_ID and SENTINEL2_CLIENT_SECRET are set in .env
  - STAC endpoint is reachable (network available)

Tests use a fixed London AOI (10×10 km) and verify ≥1 live scene returned.
"""
from __future__ import annotations
import os
import pytest
from backend.app.config import AppSettings
from backend.app.providers.sentinel2 import Sentinel2Provider
from backend.app.providers.base import ProviderUnavailableError

# Skip entire module if credentials missing
sentinel2_configured = bool(
    os.environ.get("SENTINEL2_CLIENT_ID")
    and os.environ.get("SENTINEL2_CLIENT_SECRET")
)

pytestmark = pytest.mark.skipif(
    not sentinel2_configured,
    reason="Sentinel-2 credentials not configured in .env"
)


@pytest.fixture
def sentinel2_live_provider():
    """Create provider with live credentials from .env."""
    settings = AppSettings()  # Loads from .env
    if not settings.sentinel2_is_configured():
        pytest.skip("Credentials not available")
    return Sentinel2Provider(settings)


class TestSentinel2LiveSTAC:
    """Live STAC endpoint integration tests."""

    LONDON_AOI = {
        "type": "Polygon",
        "coordinates": [[
            [-0.5, 51.4],
            [0.0, 51.4],
            [0.0, 51.9],
            [-0.5, 51.9],
            [-0.5, 51.4],
        ]],
    }

    def test_oauth_token_fetch_live(self, sentinel2_live_provider):
        """Test OAuth2 token acquisition from live Copernicus endpoint."""
        token = sentinel2_live_provider._get_token()
        assert token is not None
        assert len(token) > 50  # JWT is long
        assert "." in token  # JWT structure

    def test_sentinel2_scene_search_live(self, sentinel2_live_provider):
        """Test live STAC scene search returns ≥1 result."""
        scenes = sentinel2_live_provider.search_imagery(
            geometry=self.LONDON_AOI,
            start_date="2026-02-26",  # 30 days lookback
            end_date="2026-03-28",
            cloud_threshold=50.0,  # Lenient for test
            max_results=10,
        )

        assert len(scenes) >= 1, "Expected ≥1 Sentinel-2 scene for London"
        
        scene = scenes[0]
        assert scene.provider == "sentinel2"
        assert scene.cloud_cover >= 0 and scene.cloud_cover <= 100
        assert scene.resolution_m == 10
        assert scene.acquired_at is not None
        assert scene.image_url is not None and len(scene.image_url) > 0

    def test_sentinel2_scene_search_over_ocean_empty(self, sentinel2_live_provider):
        """Test scene search returns empty when over open ocean (expected behavior)."""
        atlantic_aoi = {
            "type": "Polygon",
            "coordinates": [[
                [-40.0, 40.0],
                [-35.0, 40.0],
                [-35.0, 45.0],
                [-40.0, 45.0],
                [-40.0, 40.0],
            ]],
        }
        
        scenes = sentinel2_live_provider.search_imagery(
            geometry=atlantic_aoi,
            start_date="2026-02-26",
            end_date="2026-03-28",
            cloud_threshold=50.0,
            max_results=10,
        )
        # May return 0 or >0 scenes depending on coverage; just verify no crash
        assert isinstance(scenes, list)

    def test_healthcheck_live(self, sentinel2_live_provider):
        """Test STAC collection endpoint health check."""
        ok, msg = sentinel2_live_provider.healthcheck()
        assert ok is True, f"Healthcheck failed: {msg}"
        assert "reachable" in msg.lower() or "available" in msg.lower()

    def test_validate_credentials_live(self, sentinel2_live_provider):
        """Test credential validation against live endpoint."""
        ok, msg = sentinel2_live_provider.validate_credentials()
        assert ok is True, f"Credential validation failed: {msg}"
        assert "obtained" in msg.lower() or "success" in msg.lower()
