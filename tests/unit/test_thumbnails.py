"""Unit tests for satellite thumbnail service and endpoint (P3-5)."""
from __future__ import annotations

import pytest

from backend.app.services.thumbnails import (
    ThumbnailCache,
    cache_key,
    clear_cache,
    get_cached_thumbnail,
    thumbnail_url,
)


SAMPLE_BBOX = [30.0, 50.0, 30.1, 50.1]
SAMPLE_SCENE = "S2A_MSIL2A_20260315"


class TestThumbnailCache:
    """LRU cache for thumbnail bytes."""

    def test_put_and_get(self):
        cache = ThumbnailCache(max_entries=4)
        cache.put("k1", b"png-data-1")
        assert cache.get("k1") == b"png-data-1"

    def test_get_missing_returns_none(self):
        cache = ThumbnailCache(max_entries=4)
        assert cache.get("missing") is None

    def test_eviction_at_capacity(self):
        cache = ThumbnailCache(max_entries=2)
        cache.put("a", b"1")
        cache.put("b", b"2")
        cache.put("c", b"3")  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == b"2"
        assert cache.get("c") == b"3"

    def test_lru_ordering(self):
        cache = ThumbnailCache(max_entries=2)
        cache.put("a", b"1")
        cache.put("b", b"2")
        cache.get("a")         # refreshes "a"
        cache.put("c", b"3")   # evicts "b" (least recent)
        assert cache.get("a") == b"1"
        assert cache.get("b") is None
        assert cache.get("c") == b"3"

    def test_size_property(self):
        cache = ThumbnailCache(max_entries=10)
        assert cache.size == 0
        cache.put("x", b"data")
        assert cache.size == 1

    def test_overwrite_same_key(self):
        cache = ThumbnailCache(max_entries=4)
        cache.put("k", b"old")
        cache.put("k", b"new")
        assert cache.get("k") == b"new"
        assert cache.size == 1


class TestCacheKey:
    """Deterministic key generation."""

    def test_same_inputs_same_key(self):
        k1 = cache_key("scene-1", [30.0, 50.0, 30.1, 50.1])
        k2 = cache_key("scene-1", [30.0, 50.0, 30.1, 50.1])
        assert k1 == k2

    def test_different_scene_different_key(self):
        k1 = cache_key("scene-1", SAMPLE_BBOX)
        k2 = cache_key("scene-2", SAMPLE_BBOX)
        assert k1 != k2

    def test_different_bbox_different_key(self):
        k1 = cache_key(SAMPLE_SCENE, [30.0, 50.0, 30.1, 50.1])
        k2 = cache_key(SAMPLE_SCENE, [31.0, 51.0, 31.1, 51.1])
        assert k1 != k2

    def test_key_length(self):
        k = cache_key(SAMPLE_SCENE, SAMPLE_BBOX)
        assert len(k) == 16


class TestThumbnailUrl:
    """URL builder for thumbnail endpoint."""

    def test_url_contains_scene_id(self):
        url = thumbnail_url(SAMPLE_SCENE, SAMPLE_BBOX)
        assert SAMPLE_SCENE in url

    def test_url_contains_key_param(self):
        url = thumbnail_url(SAMPLE_SCENE, SAMPLE_BBOX)
        assert "key=" in url

    def test_url_starts_with_api_prefix(self):
        url = thumbnail_url(SAMPLE_SCENE, SAMPLE_BBOX)
        assert url.startswith("/api/thumbnails/")


class TestThumbnailEndpoint:
    """HTTP endpoint tests."""

    def test_missing_thumbnail_returns_404(self, app_client):
        clear_cache()
        resp = app_client.get("/api/thumbnails/scene-xyz?key=nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_cached_thumbnail_returns_png(self, app_client):
        clear_cache()
        from backend.app.services.thumbnails import _cache
        _cache.put("test-key", b"\x89PNG-fake-data")
        resp = app_client.get("/api/thumbnails/scene-abc?key=test-key")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == b"\x89PNG-fake-data"

    def test_key_query_param_required(self, app_client):
        resp = app_client.get("/api/thumbnails/scene-abc")
        assert resp.status_code == 422  # missing required query param


class TestGenerateThumbnailGracefulDegradation:
    """generate_thumbnail gracefully returns None without rasterio."""

    def test_returns_none_without_rasterio(self):
        from unittest.mock import patch
        from backend.app.services.thumbnails import generate_thumbnail
        with patch("backend.app.services.thumbnails._rasterio_available", return_value=False):
            result = generate_thumbnail(
                "https://example.com/scene.tif",
                SAMPLE_BBOX,
                SAMPLE_SCENE,
            )
            assert result is None
