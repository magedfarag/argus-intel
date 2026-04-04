"""Startup smoke check — verifies the FastAPI app creates successfully."""
from __future__ import annotations


def test_app_creates_without_error():
    """App factory succeeds and /api/health route exists."""
    from app.main import app
    routes = [r.path for r in app.routes]
    assert "/api/health" in routes


def test_settings_loads_in_demo_mode(monkeypatch):
    """Settings can be loaded in demo APP_MODE."""
    monkeypatch.setenv("APP_MODE", "demo")
    from importlib import reload
    import app.config as config_module
    reload(config_module)
    settings = config_module.get_settings()
    assert settings.app_mode.value in ("demo", "staging", "production")
