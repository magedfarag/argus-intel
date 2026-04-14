"""NASA FIRMS (Fire Information for Resource Management System) connector.

Implements BaseConnector backed by the NASA FIRMS Area API.

connector_id: ``nasa-firms``
source_type:  ``public_record``

API: https://firms.modaps.eosdis.nasa.gov/api/
Free MAP_KEY available at: https://firms.modaps.eosdis.nasa.gov/api/
Use "DEMO_KEY" for rate-limited testing — register for higher limits.

Supported sources (configured via ``nasa_firms_source``):
  VIIRS_SNPP_NRT   — Suomi-NPP VIIRS Near Real Time (375 m)  ← default
  VIIRS_NOAA20_NRT — NOAA-20 VIIRS NRT (375 m)
  VIIRS_NOAA21_NRT — NOAA-21 VIIRS NRT (375 m)
  MODIS_NRT        — Terra/Aqua MODIS NRT (1 km)
  MODIS_SP         — MODIS Standard Processing (1 km)

GEOINT relevance for Gulf / MENA:
- Oil well / pipeline fires (Iraq, Kuwait, Libya)
- Conflict-related infrastructure fires (Yemen, Syria)
- Industrial fires and gas flares (Saudi Arabia, UAE, Iran)
- Agricultural burns (Nile Delta)
- Large-scale wildfire / vegetation fires

Data is public domain (US Government, CC0-equivalent).

Configure via environment variables:
  NASA_FIRMS_MAP_KEY      — Your FIRMS MAP_KEY (default "DEMO_KEY")
  NASA_FIRMS_SOURCE       — FIRMS product name (default VIIRS_SNPP_NRT)
  NASA_FIRMS_API_URL      — Override endpoint
  NASA_FIRMS_DAYS_LOOKBACK — Days of archive to query (1–10, default 2)
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    ConnectorUnavailableError,
    NormalizationError,
)
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    ThermalAnomalyAttributes,
    make_event_id,
)

log = logging.getLogger(__name__)

_DEFAULT_API_URL = "https://firms.modaps.eosdis.nasa.gov/api"
_DEFAULT_SOURCE = "VIIRS_SNPP_NRT"
_DEFAULT_MAP_KEY = "DEMO_KEY"

# NASA FIRMS data is produced by the US Government and is public domain.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="allowed",
    redistribution="allowed",
    attribution_required=True,
)

# FIRMS satellite code → readable name
_SATELLITE_NAMES: dict[str, str] = {
    "T": "Terra (MODIS)",
    "A": "Aqua (MODIS)",
    "S": "Suomi-NPP (VIIRS)",
    "N": "NOAA-20 (VIIRS J1)",
    "1": "NOAA-21 (VIIRS J2)",
}

# VIIRS confidence: h=high, n=nominal, l=low
# MODIS confidence: integer 0-100
_VIIRS_CONF_SCORE: dict[str, float] = {
    "h": 0.95,
    "high": 0.95,
    "n": 0.75,
    "nominal": 0.75,
    "l": 0.45,
    "low": 0.45,
}


def _bbox_from_geojson(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon)."""
    gtype = geometry.get("type", "")
    coords: list[list[float]] = []
    if gtype == "Point":
        coords = [geometry["coordinates"]]
    elif gtype == "Polygon":
        coords = geometry["coordinates"][0]
    elif gtype == "MultiPolygon":
        for poly in geometry["coordinates"]:
            coords.extend(poly[0])
    else:
        raise NormalizationError(f"Unsupported geometry type: {gtype!r}")
    lons = [float(c[0]) for c in coords]
    lats = [float(c[1]) for c in coords]
    return min(lats), min(lons), max(lats), max(lons)


def _confidence_score(raw_conf: str, is_viirs: bool) -> float:
    """Map FIRMS confidence field → normalised 0–1 score."""
    if is_viirs:
        return _VIIRS_CONF_SCORE.get(str(raw_conf).lower(), 0.70)
    # MODIS: 0-100 integer
    try:
        return max(0.0, min(1.0, int(raw_conf) / 100.0))
    except (ValueError, TypeError):
        return 0.70


class NasaFirmsConnector(BaseConnector):
    """NASA FIRMS Active Fire / Thermal Anomaly connector.

    Produces ``thermal_anomaly_event`` CanonicalEvents for VIIRS or MODIS
    fire detections within the query AOI.  Each event represents a single
    ~375 m (VIIRS) or ~1 km (MODIS) fire pixel detected in the last
    ``days_lookback`` days.

    Particularly relevant for Gulf/MENA:
    - Gas flare and oil field fires (Iraq, Kuwait, Libya, Saudi Arabia)
    - Conflict-triggered infrastructure fires (Yemen, Syria, Gaza)
    - Industrial accidents (refineries, petrochemical plants)
    """

    connector_id = "nasa-firms"
    display_name = "NASA FIRMS (Active Fire / Thermal Anomaly)"
    source_type = "public_record"

    def __init__(
        self,
        *,
        map_key: str = _DEFAULT_MAP_KEY,
        api_url: str = _DEFAULT_API_URL,
        source: str = _DEFAULT_SOURCE,
        days_lookback: int = 2,
        http_timeout: float = 60.0,
    ) -> None:
        self._map_key = map_key
        self._api_url = api_url.rstrip("/")
        self._source = source
        self._days_lookback = max(1, min(10, days_lookback))
        self._http_timeout = http_timeout
        self._is_viirs = "VIIRS" in source.upper()

    def _area_url(self, min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
        """Build the FIRMS area JSON URL for the given bbox and configured source."""
        bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        return f"{self._api_url}/area/json/{self._map_key}/{self._source}/{bbox}/{self._days_lookback}"

    # ── BaseConnector interface ───────────────────────────────────────────────

    def connect(self) -> None:
        """Health-check: probe FIRMS with a 1°×1° null-island bbox (FIRMS requires non-trivial area)."""
        url = self._area_url(0.0, 0.0, 1.0, 1.0)
        try:
            resp = httpx.get(url, timeout=20.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"NASA FIRMS unreachable: {exc}") from exc

    def fetch(
        self,
        geometry: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        *,
        max_results: int = 500,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch thermal anomaly detections in the AOI bbox.

        FIRMS returns all detections for the configured ``days_lookback``
        window; the ``start_time``/``end_time`` parameters are not used by the
        FIRMS Area API but are kept for interface compatibility.
        """
        try:
            min_lat, min_lon, max_lat, max_lon = _bbox_from_geojson(geometry)
        except NormalizationError as exc:
            log.warning("Cannot derive bbox from geometry: %s", exc)
            return []

        url = self._area_url(min_lat, min_lon, max_lat, max_lon)
        try:
            resp = httpx.get(url, timeout=self._http_timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"FIRMS fetch failed: {exc}") from exc

        detections = resp.json()
        if not isinstance(detections, list):
            log.warning("FIRMS returned non-list response: %s", type(detections).__name__)
            return []
        log.debug("NASA FIRMS: %d thermal anomaly pixels returned", len(detections))
        return detections[:max_results]

    def normalize(self, raw: dict[str, Any]) -> CanonicalEvent:
        """Transform a FIRMS fire pixel dict → ``thermal_anomaly_event``."""
        acq_date = str(raw.get("acq_date", ""))
        acq_time = str(raw.get("acq_time", "0000")).zfill(4)
        if not acq_date:
            raise NormalizationError("FIRMS record missing 'acq_date'")

        try:
            lat = float(raw["latitude"])
            lon = float(raw["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            raise NormalizationError(f"FIRMS record has invalid coordinates: {exc}") from exc

        # Parse event time
        try:
            event_time = datetime.strptime(
                f"{acq_date}T{acq_time[:2]}:{acq_time[2:]}", "%Y-%m-%dT%H:%M"
            ).replace(tzinfo=UTC)
        except ValueError:
            try:
                event_time = datetime.strptime(acq_date, "%Y-%m-%d").replace(
                    tzinfo=UTC
                )
            except ValueError as exc:
                raise NormalizationError(f"Cannot parse FIRMS date {acq_date!r}: {exc}") from exc

        geom = {"type": "Point", "coordinates": [lon, lat]}

        # Handle VIIRS uses bright_ti4, MODIS uses brightness
        brightness = None
        raw_brightness = raw.get("bright_ti4") or raw.get("brightness")
        if raw_brightness is not None:
            try:
                brightness = float(raw_brightness)
            except (ValueError, TypeError):
                pass

        frp = None
        if raw.get("frp") is not None:
            try:
                frp = float(raw["frp"])
            except (ValueError, TypeError):
                pass

        raw_sat = str(raw.get("satellite", ""))
        satellite = _SATELLITE_NAMES.get(raw_sat, raw_sat or None)
        instrument = "VIIRS" if self._is_viirs else "MODIS"

        raw_conf = str(raw.get("confidence", ""))
        conf_score = _confidence_score(raw_conf, self._is_viirs)

        native_id = hashlib.sha256(
            f"{lat:.5f}:{lon:.5f}:{acq_date}:{acq_time}:{self._source}".encode()
        ).hexdigest()[:20]
        dedupe = hashlib.sha256(f"firms:{native_id}".encode()).hexdigest()[:16]

        attrs = ThermalAnomalyAttributes(
            satellite=satellite,
            instrument=instrument,
            frp=frp,
            brightness=brightness,
            bright_t31=float(raw["bright_t31"]) if raw.get("bright_t31") else None,
            confidence=raw_conf or None,
            track=float(raw["track"]) if raw.get("track") else None,
            scan=float(raw["scan"]) if raw.get("scan") else None,
            acq_date=acq_date,
            acq_time=acq_time,
            day_night=raw.get("daynight") or None,
            version=raw.get("version") or None,
            source_dataset=self._source,
        )

        return CanonicalEvent(
            event_id=make_event_id("nasa-firms", native_id, event_time.isoformat()),
            source="nasa-firms",
            source_type=SourceType.PUBLIC_RECORD,
            entity_type=EntityType.THERMAL_ANOMALY,
            entity_id=native_id,
            event_type=EventType.THERMAL_ANOMALY_EVENT,
            event_time=event_time,
            geometry=geom,
            centroid=geom,
            confidence=conf_score,
            quality_flags=["thermal-anomaly", self._source.lower()],
            attributes=attrs.model_dump(),
            normalization=NormalizationRecord(
                normalized_by="connector.nasa.firms",
                dedupe_key=dedupe,
            ),
            provenance=ProvenanceRecord(
                raw_source_ref=f"firms://{self._source}/{native_id}",
                source_record_id=native_id,
                source_url="https://firms.modaps.eosdis.nasa.gov/",
            ),
            correlation_keys=CorrelationKeys(),
            license=_LICENSE,
        )

    def health(self) -> ConnectorHealthStatus:
        """Probe FIRMS API availability."""
        try:
            url = self._area_url(0.0, 0.0, 0.001, 0.001)
            resp = httpx.get(url, timeout=15.0)
            resp.raise_for_status()
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=True,
                message=f"NASA FIRMS reachable (HTTP {resp.status_code})",
                last_successful_poll=datetime.now(UTC),
            )
        except Exception as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
