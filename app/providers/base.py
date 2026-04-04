"""Abstract base class for all satellite imagery providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from app.models.scene import SceneMetadata


class ProviderUnavailableError(Exception):
    """Raised when a provider cannot fulfil a request."""


class SatelliteProvider(ABC):
    """Common interface every satellite provider must implement."""

    #: Short identifier used in API responses and config (no spaces).
    provider_name: str = "base"
    display_name: str = "Base Provider"
    resolution_m: int = 0

    @abstractmethod
    def validate_credentials(self) -> Tuple[bool, str]:
        """Return (is_valid, reason_if_invalid).

        Must not make network calls unless necessary; prefer local secret
        presence checks first, then a lightweight API ping.
        """

    @abstractmethod
    def search_imagery(
        self,
        geometry: Dict[str, Any],
        start_date: str,
        end_date: str,
        cloud_threshold: float = 20.0,
        max_results: int = 10,
    ) -> List[SceneMetadata]:
        """Search for scenes intersecting *geometry* within the date range.

        Returns a list of SceneMetadata ordered by acquisition date (newest first).
        Must raise ProviderUnavailableError if the provider is not reachable.
        """

    @abstractmethod
    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        """Retrieve full metadata for a single scene by ID."""

    @abstractmethod
    def healthcheck(self) -> Tuple[bool, str]:
        """Lightweight connectivity check.  Returns (ok, message)."""

    def get_quota_status(self) -> Dict[str, Any]:
        """Return quota / rate-limit information.  Optional to override."""
        return {"available": True, "note": "quota tracking not implemented"}

    def download_assets(
        self,
        scene_id: str,
        bands: List[str],
        target_dir: str,
    ) -> Dict[str, str]:
        """Download band assets to *target_dir*.  Returns band -> path map.

        Default implementation raises NotImplementedError.
        Providers that support COG streaming do not need to override this.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support bulk download"
        )

    def get_capabilities(self) -> Dict[str, Any]:
        """Return a summary of provider capabilities."""
        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "resolution_m": self.resolution_m,
            "supports_cog_streaming": False,
            "supports_bulk_download": False,
            "requires_credentials": False,
        }
