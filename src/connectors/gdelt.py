"""GDELT Global Database of Events, Language, and Tone — DOC 2.0 connector.

P2-1.1: Implements BaseConnector backed by the GDELT DOC 2.0 article-list API.
P2-1.2: AOI/time/theme search via `sourcecountry:` + `theme:` query terms.
P2-1.3: Normalizes raw articles → `contextual_event` CanonicalEvents.

connector_id: `gdelt-doc`
source_type:  `context_feed`

GDELT is public domain; no credentials required.  Articles are fetched at the
country granularity (derived from AOI centroid) because the free-tier DOC 2.0
API does not support bounding-box geographic queries.  Exact article locations
are unavailable in artlist mode; events carry the AOI centroid as a proxy.

Rate-limit guidance: GDELT recommends ≤1 req/10 s for unregistered clients.
The Celery beat scheduler in `app.workers.tasks` respects a 15-minute cadence.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    ConnectorUnavailableError,
    NormalizationError,
)
from src.models.canonical_event import (
    CanonicalEvent,
    ContextualAttributes,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT is public domain per their terms; commercial use is permitted.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="allowed",
    redistribution="allowed",
    attribution_required=True,
)

# Approximate bounding boxes for Middle East / North Africa countries,
# used to infer a `sourcecountry:` filter from the AOI centroid.
# Format: (min_lon, min_lat, max_lon, max_lat)
_COUNTRY_BOUNDS: Dict[str, Tuple[float, float, float, float]] = {
    "Saudi Arabia": (36.5, 16.3, 55.7, 32.2),
    "UAE": (51.5, 22.6, 56.4, 26.1),
    "Qatar": (50.7, 24.4, 51.7, 26.2),
    "Kuwait": (46.5, 28.5, 48.5, 30.1),
    "Bahrain": (50.3, 25.8, 50.8, 26.4),
    "Oman": (51.8, 16.6, 59.9, 26.4),
    "Yemen": (42.5, 12.1, 54.5, 19.0),
    "Iraq": (38.7, 29.1, 48.6, 37.4),
    "Syria": (35.7, 32.3, 42.4, 37.3),
    "Jordan": (34.9, 29.2, 39.3, 33.4),
    "Lebanon": (35.1, 33.1, 36.6, 34.7),
    "Egypt": (24.7, 22.0, 37.1, 31.7),
    "Libya": (9.3, 19.5, 25.2, 33.2),
    "Iran": (44.0, 25.1, 63.3, 39.8),
    "Turkey": (26.0, 36.0, 44.8, 42.1),
}

# Construction-relevant GDELT Tier 1 / 2 theme codes
DEFAULT_CONSTRUCTION_THEMES = [
    "ECON_HOUSING",
    "ECON_INFRA",
    "ENV_DEFORESTATION",
]


def _centroid_from_geometry(geometry: Dict[str, Any]) -> Tuple[float, float]:
    """Return (lon, lat) centroid of a GeoJSON geometry.

    Supports Point, Polygon, and MultiPolygon.
    Raises NormalizationError for unsupported types.
    """
    geom_type = geometry.get("type", "")
    coords = geometry.get("coordinates", [])

    if geom_type == "Point":
        return float(coords[0]), float(coords[1])

    if geom_type == "Polygon" and coords:
        ring = coords[0]
        lons = [float(pt[0]) for pt in ring]
        lats = [float(pt[1]) for pt in ring]
        return sum(lons) / len(lons), sum(lats) / len(lats)

    if geom_type == "MultiPolygon" and coords:
        ring = coords[0][0]
        lons = [float(pt[0]) for pt in ring]
        lats = [float(pt[1]) for pt in ring]
        return sum(lons) / len(lons), sum(lats) / len(lats)

    raise NormalizationError(f"Unsupported geometry type for centroid: {geom_type!r}")


def _country_from_centroid(lon: float, lat: float) -> Optional[str]:
    """Return GDELT-recognised country name for a centroid, or None."""
    for country, (min_lon, min_lat, max_lon, max_lat) in _COUNTRY_BOUNDS.items():
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return country
    return None


def _parse_gdelt_datetime(seendate: str) -> datetime:
    """Parse GDELT seendate format `20260403T120000Z` into UTC datetime."""
    try:
        return datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise NormalizationError(f"Cannot parse GDELT seendate {seendate!r}: {exc}") from exc


class GdeltConnector(BaseConnector):
    """GDELT DOC 2.0 article-list connector for contextual event enrichment.

    Fetches English-language news events intersecting a geographic AOI and
    optional GDELT theme codes, then normalises them to `contextual_event`
    CanonicalEvents.

    The GDELT API is public and does not require credentials.  Articles do not
    carry precise lat/lon in artlist mode; `fetch()` enriches each raw record
    with the AOI centroid (`_aoi_lon`, `_aoi_lat`) so `normalize()` can
    produce a useful (if approximate) geometry.
    """

    connector_id = "gdelt-doc"
    display_name = "GDELT (Global Database of Events, Language, and Tone)"
    source_type = "context_feed"

    def __init__(
        self,
        *,
        api_base: str = _API_BASE,
        http_timeout: float = 30.0,
        default_themes: Optional[List[str]] = None,
        default_language: str = "english",
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._http_timeout = http_timeout
        self._default_themes = default_themes if default_themes is not None else []
        self._default_language = default_language

    # ── BaseConnector interface ───────────────────────────────────────────────

    def connect(self) -> None:
        """Verify the GDELT DOC API is reachable with a minimal test request."""
        params: Dict[str, Any] = {
            "query": "test",
            "mode": "artlist",
            "format": "json",
            "maxrecords": "1",
        }
        try:
            resp = httpx.get(self._api_base, params=params, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"GDELT API unreachable: {exc}") from exc

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        *,
        themes: Optional[List[str]] = None,
        max_results: int = 50,
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch GDELT articles for an AOI + time window.

        Geographic filtering derives a `sourcecountry:` term from the AOI
        centroid using `_COUNTRY_BOUNDS`.  Theme codes are appended as
        `theme:` terms.  Each returned raw article is enriched with
        `_aoi_lon` / `_aoi_lat` for downstream `normalize()` calls.

        Args:
            geometry: GeoJSON geometry dict for the AOI.
            start_time: UTC-aware start of the search window.
            end_time:   UTC-aware end of the search window.
            themes:     GDELT theme codes to filter by (e.g. `ECON_INFRA`).
            max_results: Maximum number of articles to return (cap: 250).
            language:   GDELT sourcelang value (default: `english`).

        Returns:
            List of raw GDELT article dicts (may be empty).
        """
        query_parts: List[str] = []
        aoi_lon, aoi_lat = 0.0, 0.0

        try:
            aoi_lon, aoi_lat = _centroid_from_geometry(geometry)
            country = _country_from_centroid(aoi_lon, aoi_lat)
            if country:
                query_parts.append(f'sourcecountry:"{country}"')
        except NormalizationError:
            logger.warning(
                "GdeltConnector: cannot compute centroid — no geographic filter applied"
            )

        active_themes = themes if themes is not None else self._default_themes
        for theme in active_themes:
            query_parts.append(f"theme:{theme}")

        # Ensure we always have a non-empty query string
        query = " ".join(query_parts) if query_parts else "construction urban"

        params: Dict[str, Any] = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "startdatetime": start_time.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end_time.strftime("%Y%m%d%H%M%S"),
            "maxrecords": min(max_results, 250),
            "sort": "DateDesc",
        }
        lang = language if language is not None else self._default_language
        if lang:
            params["sourcelang"] = lang

        try:
            resp = httpx.get(self._api_base, params=params, timeout=self._http_timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(f"GDELT fetch failed: {exc}") from exc

        articles: List[Dict[str, Any]] = resp.json().get("articles") or []

        # Enrich with AOI centroid so normalize() can produce a spatial event
        for article in articles:
            article["_aoi_lon"] = aoi_lon
            article["_aoi_lat"] = aoi_lat

        return articles

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Convert a GDELT article dict to a `contextual_event` CanonicalEvent.

        The article's URL is the stable entity identifier.  Geometry uses the
        AOI centroid injected by `fetch()` (`_aoi_lon` / `_aoi_lat`),
        or `[0.0, 0.0]` (null island) with a quality flag when unavailable.
        """
        url = raw.get("url", "")
        title = raw.get("title", "")
        seendate = raw.get("seendate", "")

        if not url and not title:
            raise NormalizationError("GDELT article missing both url and title")

        event_time = (
            _parse_gdelt_datetime(seendate)
            if seendate
            else datetime.now(timezone.utc)
        )

        entity_id = (url or title)[:200]
        event_id = make_event_id("gdelt-doc", entity_id, event_time.isoformat())

        # Spatial proxy: use AOI centroid injected by fetch()
        lon = float(raw.get("_aoi_lon", 0.0))
        lat = float(raw.get("_aoi_lat", 0.0))
        quality_flags: List[str] = []
        if lon == 0.0 and lat == 0.0:
            quality_flags.append("geometry-unavailable")

        point = {"type": "Point", "coordinates": [lon, lat]}

        attributes = ContextualAttributes(
            headline=title or None,
            url=url or None,
            source_publication=raw.get("domain") or None,
            language=raw.get("language") or None,
        )

        return CanonicalEvent(
            event_id=event_id,
            source="gdelt-doc",
            source_type=SourceType.CONTEXT_FEED,
            entity_type=EntityType.NEWS_ARTICLE,
            event_type=EventType.CONTEXTUAL_EVENT,
            entity_id=entity_id,
            event_time=event_time,
            geometry=point,
            centroid=point,
            confidence=0.5,
            quality_flags=quality_flags,
            attributes=attributes.model_dump(),
            normalization=NormalizationRecord(
                normalized_by="connector.gdelt.doc",
                normalization_warnings=(
                    ["geometry-approximated-from-aoi-centroid"]
                    if (lon != 0.0 or lat != 0.0)
                    else ["geometry-unavailable-artlist-mode"]
                ),
            ),
            provenance=ProvenanceRecord(
                raw_source_ref=f"gdelt://doc/{hashlib.sha256((url or title).encode()).hexdigest()[:16]}",
                source_record_id=url or None,
                source_url=url or None,
            ),
            license=_LICENSE,
        )

    def normalize_all(self, raw_records: List[Dict[str, Any]]) -> List[CanonicalEvent]:
        """Normalize a batch of GDELT articles, skipping any that fail."""
        events: List[CanonicalEvent] = []
        for raw in raw_records:
            try:
                events.append(self.normalize(raw))
            except NormalizationError as exc:
                logger.warning("GdeltConnector.normalize_all: skipped record — %s", exc)
        return events

    def health(self) -> ConnectorHealthStatus:
        """Return a lightweight health snapshot for the GDELT DOC API."""
        try:
            self.connect()
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=True,
                message="GDELT DOC API reachable",
            )
        except ConnectorUnavailableError as exc:
            return ConnectorHealthStatus(
                connector_id=self.connector_id,
                healthy=False,
                message=str(exc),
            )
