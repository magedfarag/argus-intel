"""Unit tests for AppSettings."""
from __future__ import annotations
from app.config import AppMode, AppSettings, get_settings

def test_defaults_are_safe():
    s = AppSettings()
    assert s.app_mode == AppMode.STAGING
    assert s.sentinel2_client_id == ""
    assert s.cache_ttl_seconds == 3600

def test_sentinel2_not_configured_by_default():
    assert AppSettings().sentinel2_is_configured() is False

def test_landsat_always_configured():
    assert AppSettings().landsat_is_configured() is True

def test_effective_celery_broker_falls_back_to_redis():
    s = AppSettings(redis_url="redis://localhost:6379/0")
    assert s.effective_celery_broker() == "redis://localhost:6379/0"

def test_redis_available_false_when_empty():
    assert AppSettings(redis_url="").redis_available() is False

def test_log_level_uppercased():
    assert AppSettings(log_level="debug").log_level == "DEBUG"

def test_get_settings_returns_singleton():
    assert get_settings() is get_settings()
