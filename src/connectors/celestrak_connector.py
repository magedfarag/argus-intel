"""CelesTrak GP live connector — ORB-01.

Fetches active-satellite TLE data from the CelesTrak General Perturbations
(GP) public endpoint.  No authentication is required.

connector_id: ``celestrak-gp-live``
source_type:  ``telemetry``
endpoint:     ``https://celestrak.org/satcat/gp.php?GROUP=active&FORMAT=tle``

Design notes:
- ``fetch()`` downloads the full active-satellite catalogue and parses it into
  a list of raw ``{"name", "line1", "line2"}`` dicts.
- ``normalize()`` converts one such dict into a ``CanonicalEvent``, reusing
  ``orbit_to_canonical_event()`` from the stub connector module.
- ``fetch_all_tles()`` is the high-level method consumed by
  ``OrbitLayerService.refresh()``; it returns ``SatelliteOrbit`` objects.
- ``ingest_orbits()`` parses an explicit TLE block without a live fetch (used
  by the ``/ingest`` endpoint via ``OrbitLayerService.ingest_tle()``).
- ``compute_passes()`` delegates to an internal stub connector instance so
  pass prediction works regardless of network access.
- HTTP errors are wrapped in ``ConnectorError``; network failures in the same.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorHealthStatus,
    NormalizationError,
)
from src.connectors.orbit_connector import (
    OrbitConnector,
    _parse_tle_triplet,
    orbit_to_canonical_event,
)
from src.models.canonical_event import CanonicalEvent
from src.models.operational_layers import SatelliteOrbit

logger = logging.getLogger(__name__)

_GP_URL = "https://celestrak.org/satcat/gp.php?GROUP=active&FORMAT=tle"
_SOURCE = "celestrak_gp_live"


# ── TLE text parser ───────────────────────────────────────────────────────────


def _parse_tle_text(text: str) -> list[dict[str, Any]]:
    """Parse a block of TLE text into raw name/line1/line2 dicts.

    Blank lines and lines starting with ``#`` are skipped.  Any partial
    triplet at the end of the input is silently discarded.
    """
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    result: list[dict[str, Any]] = []
    i = 0
    while i + 2 < len(lines):
        name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
        if line1.startswith("1 ") and line2.startswith("2 "):
            result.append(
                {
                    "name": name.strip(),
                    "line1": line1.strip(),
                    "line2": line2.strip(),
                }
            )
            i += 3
        else:
            i += 1
    return result


# ── CelestrakConnector ────────────────────────────────────────────────────────


class CelestrakConnector(BaseConnector):
    """Live connector for CelesTrak GP active-satellite TLE data.

    The ``OrbitLayerService`` will call ``fetch_all_tles()`` during
    ``refresh()`` and ``ingest_orbits()`` during manual TLE injection.
    """

    connector_id: str = "celestrak-gp-live"
    display_name: str = "CelesTrak GP Live"
    source_type: str = "telemetry"

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout
        self._connected: bool = False
        self._last_success: datetime | None = None
        self._error_count: int = 0
        # Delegate stub instance for ingest_orbits / compute_passes reuse.
        self._delegate = OrbitConnector()

    # ── BaseConnector abstract methods ────────────────────────────────────────

    def connect(self) -> None:
        """Verify the CelesTrak GP endpoint is reachable via a HEAD probe.

        Raises:
            ConnectorError: on network failure or non-2xx / non-405 response.
        """
        try:
            resp = httpx.head(_GP_URL, timeout=self._timeout, follow_redirects=True)
            # 405 Method Not Allowed: HEAD not supported but server is up.
            if resp.status_code != 405:
                resp.raise_for_status()
            self._connected = True
            logger.info(
                "CelestrakConnector: endpoint reachable (HTTP %d)", resp.status_code
            )
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(
                f"CelestrakConnector: endpoint returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                f"CelestrakConnector: endpoint unreachable: {exc}"
            ) from exc

    def fetch(
        self,
        geometry: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch live TLE data from the CelesTrak GP endpoint.

        ``geometry`` and ``start_time``/``end_time`` are ignored — CelesTrak
        returns the full active-satellite catalogue regardless of filter.

        Returns:
            List of dicts with keys ``name``, ``line1``, ``line2``.

        Raises:
            ConnectorError: on HTTP error or network failure.
        """
        try:
            resp = httpx.get(_GP_URL, timeout=self._timeout, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._error_count += 1
            raise ConnectorError(
                f"CelestrakConnector: HTTP {exc.response.status_code} from GP endpoint"
            ) from exc
        except httpx.HTTPError as exc:
            self._error_count += 1
            raise ConnectorError(
                f"CelestrakConnector: network failure fetching TLEs: {exc}"
            ) from exc

        return _parse_tle_text(resp.text)

    def normalize(self, raw: dict[str, Any]) -> CanonicalEvent:
        """Transform a raw TLE dict (name/line1/line2) into a CanonicalEvent.

        Raises:
            NormalizationError: if ``raw`` is missing required fields or
                                 the TLE cannot be parsed.
        """
        try:
            orbit = _parse_tle_triplet(raw["name"], raw["line1"], raw["line2"])
            orbit = orbit.model_copy(update={"source": _SOURCE})
        except KeyError as exc:
            raise NormalizationError(
                f"CelestrakConnector.normalize: missing field {exc}"
            ) from exc
        except Exception as exc:
            raise NormalizationError(
                f"CelestrakConnector.normalize: TLE parse error: {exc}"
            ) from exc
        return orbit_to_canonical_event(orbit)

    def health(self) -> ConnectorHealthStatus:
        """Return a lightweight health snapshot."""
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=self._connected and self._error_count == 0,
            message=(
                f"Live GP connector; errors={self._error_count}"
                if self._connected
                else "Not yet connected"
            ),
            last_successful_poll=self._last_success,
            error_count=self._error_count,
        )

    # ── Orbit-specific public API (consumed by OrbitLayerService) ─────────────

    def fetch_all_tles(self) -> list[SatelliteOrbit]:
        """Fetch live TLEs and return as ``SatelliteOrbit`` objects.

        Called by ``OrbitLayerService.refresh()`` when this connector is active.

        Raises:
            ConnectorError: propagated from ``fetch()``.
        """
        now = datetime.now(UTC)
        raw_dicts = self.fetch({}, now, now)
        orbits: list[SatelliteOrbit] = []
        loaded_at = datetime.now(UTC)
        for d in raw_dicts:
            try:
                orbit = _parse_tle_triplet(d["name"], d["line1"], d["line2"])
                orbit = orbit.model_copy(update={"source": _SOURCE, "loaded_at": loaded_at})
                self._delegate._orbits[orbit.satellite_id] = orbit
                orbits.append(orbit)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "CelestrakConnector: skipping malformed TLE '%s': %s",
                    d.get("name", "?"),
                    exc,
                )
        self._last_success = datetime.now(UTC)
        logger.info("CelestrakConnector: ingested %d orbits from live feed", len(orbits))
        return orbits

    def ingest_orbits(self, tle_text: str) -> list[SatelliteOrbit]:
        """Parse explicit TLE text without a live fetch.

        Delegates parsing to the stub connector for consistent field extraction,
        then re-stamps the ``source`` field to ``celestrak_gp_live``.

        Used by ``OrbitLayerService.ingest_tle()`` (manual TLE injection endpoint).
        """
        orbits = self._delegate.ingest_orbits(tle_text)
        return [o.model_copy(update={"source": _SOURCE}) for o in orbits]

    def compute_passes(
        self,
        satellite_id: str,
        lon: float,
        lat: float,
        horizon_hours: int,
    ) -> list:
        """Delegate pass computation to the internal stub connector."""
        return self._delegate.compute_passes(satellite_id, lon, lat, horizon_hours)
