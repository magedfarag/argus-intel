"""ProviderRegistry — central access point for all providers.

The registry is instantiated once at application startup, calls
validate_credentials() on each provider, and caches their availability
status.  FastAPI dependency injection (dependencies.py) exposes it.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.config import AppMode
from app.providers.base import ProviderUnavailableError, SatelliteProvider

log = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, SatelliteProvider] = {}
        self._availability: Dict[str, Tuple[bool, str]] = {}

    def register(self, provider: SatelliteProvider) -> None:
        """Register a provider and check its credentials."""
        name = provider.provider_name
        self._providers[name] = provider
        ok, reason = provider.validate_credentials()
        self._availability[name] = (ok, reason)
        level = logging.INFO if ok else logging.WARNING
        log.log(level, "Provider %s: %s — %s", name, "OK" if ok else "unavailable", reason)

    def get(self, name: str) -> Optional[SatelliteProvider]:
        return self._providers.get(name)

    def is_available(self, name: str) -> bool:
        ok, _ = self._availability.get(name, (False, "not registered"))
        return ok

    def get_availability(self, name: str) -> Tuple[bool, str]:
        return self._availability.get(name, (False, "not registered"))

    def all_providers(self) -> List[SatelliteProvider]:
        return list(self._providers.values())

    def available_providers(self) -> List[SatelliteProvider]:
        return [p for p in self._providers.values() if self.is_available(p.provider_name)]

    def select_provider(self, name: str, mode: Optional[AppMode] = None) -> Optional[SatelliteProvider]:
        """Select a provider by name; return None if unavailable.

        When *mode* is supplied:
        - PRODUCTION: demo is never returned (returns None instead)
        - DEMO: always returns the demo provider directly
        - STAGING/None: no restriction on demo
        """
        from app.config import AppMode
        if name == "auto":
            if mode == AppMode.DEMO:
                return self._providers.get("demo")
            # Prefer live providers first
            for pref in ("sentinel2", "landsat", "maxar", "planet"):
                if self.is_available(pref):
                    return self._providers[pref]
            # Only offer demo as auto-fallback in non-production modes
            if mode != AppMode.PRODUCTION and self.is_available("demo"):
                return self._providers["demo"]
            return None
        p = self._providers.get(name)
        if p and self.is_available(name):
            # In production mode, demo is never a valid resolved provider
            if mode == AppMode.PRODUCTION and p.provider_name == "demo":
                return None
            return p
        return None

    def select_provider_by_mode(self, mode: AppMode) -> Tuple[List[str], str]:
        """Return (priority_list, description) for providers in given mode.
        
        - DEMO: [demo]
        - STAGING: [sentinel2, landsat, demo]
        - PRODUCTION: [sentinel2, landsat]
        """
        if mode == AppMode.DEMO:
            return ["demo"], "Demo mode: DemoProvider only"
        elif mode == AppMode.STAGING:
            return ["sentinel2", "landsat", "maxar", "planet", "demo"], "Staging mode: real providers with demo fallback"
        elif mode == AppMode.PRODUCTION:
            return ["sentinel2", "landsat", "maxar", "planet"], "Production mode: real providers only, fail-fast"
        else:
            raise ValueError(f"Unknown AppMode: {mode}")

    def health_all(self) -> Dict[str, Tuple[bool, str]]:
        """Re-run healthcheck on each provider (live network calls). """
        results: Dict[str, Tuple[bool, str]] = {}
        for name, provider in self._providers.items():
            try:
                ok, msg = provider.healthcheck()
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, str(exc)
            results[name] = (ok, msg)
        return results
