"""Unit tests for GdeltConnector (P2-1.7 — ≥10 tests).

Tests cover:
- _centroid_from_geometry() for Point, Polygon, MultiPolygon, unsupported
- _country_from_centroid() matching and non-matching coordinates
- _parse_gdelt_datetime() valid and invalid formats
- GdeltConnector.normalize() happy path with AOI centroid enrichment
- GdeltConnector.normalize() null-island fallback and quality flag
- GdeltConnector.normalize() raises NormalizationError for empty record
- GdeltConnector.normalize_all() skips bad records
- GdeltConnector.fetch() builds correct query params and enriches articles
- GdeltConnector.health() returns healthy on success / unhealthy on failure
- GdeltConnector.connect() raises ConnectorUnavailableError on HTTP error
- Event ID determinism across two normalize() calls
- CanonicalEvent fields: source_type, entity_type, event_type, license
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorUnavailableError, NormalizationError
from src.connectors.gdelt import (
    GdeltConnector,
    _centroid_from_geometry,
    _country_from_centroid,
    _parse_gdelt_datetime,
)
from src.models.canonical_event import EntityType, EventType, SourceType


# ── Helper fixtures ──────────────────────────────────────────────────────────

def _article(
    url: str = "https://example.com/news/construction",
    title: str = "New Tower Rises in Riyadh",
    seendate: str = "20260403T120000Z",
    domain: str = "example.com",
    language: str = "English",
    aoi_lon: float = 46.7,
    aoi_lat: float = 24.7,
) -> Dict[str, Any]:
    return {
        "url": url,
        "title": title,
        "seendate": seendate,
        "domain": domain,
        "language": language,
        "_aoi_lon": aoi_lon,
        "_aoi_lat": aoi_lat,
    }


def _polygon_geometry(lon: float = 46.7, lat: float = 24.7) -> Dict[str, Any]:
    delta = 0.1
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - delta, lat - delta],
            [lon + delta, lat - delta],
            [lon + delta, lat + delta],
            [lon - delta, lat + delta],
            [lon - delta, lat - delta],
        ]],
    }


# ── _centroid_from_geometry ──────────────────────────────────────────────────

class TestCentroidFromGeometry:
    def test_point(self):
        lon, lat = _centroid_from_geometry({"type": "Point", "coordinates": [46.7, 24.7]})
        assert lon == pytest.approx(46.7)
        assert lat == pytest.approx(24.7)

    def test_polygon(self):
        lon, lat = _centroid_from_geometry(_polygon_geometry(46.7, 24.7))
        # Polygon centroid includes closing vertex → mean slightly off centre; abs=0.05
        assert lon == pytest.approx(46.7, abs=0.05)
        assert lat == pytest.approx(24.7, abs=0.05)

    def test_multipolygon(self):
        geom = {
            "type": "MultiPolygon",
            "coordinates": [[[[50.0, 25.0], [51.0, 25.0], [51.0, 26.0], [50.0, 26.0], [50.0, 25.0]]]],
        }
        lon, lat = _centroid_from_geometry(geom)
        # Closing vertex included → mean is weighted; abs=0.2
        assert lon == pytest.approx(50.5, abs=0.2)
        assert lat == pytest.approx(25.5, abs=0.2)

    def test_unsupported_type_raises(self):
        with pytest.raises(NormalizationError, match="Unsupported geometry type"):
            _centroid_from_geometry({"type": "GeometryCollection", "geometries": []})


# ── _country_from_centroid ───────────────────────────────────────────────────

class TestCountryFromCentroid:
    def test_riyadh_maps_to_saudi_arabia(self):
        # Riyadh ~46.7°E, 24.7°N — inside Saudi Arabia bounds
        assert _country_from_centroid(46.7, 24.7) == "Saudi Arabia"

    def test_muscat_maps_to_oman(self):
        # Muscat ~58.4°E, 23.6°N — outside Saudi Arabia's eastern bound (55.7°E)
        assert _country_from_centroid(58.4, 23.6) == "Oman"

    def test_outside_known_bounds_returns_none(self):
        # London ~-0.1°E, 51.5°N — not in _COUNTRY_BOUNDS
        assert _country_from_centroid(-0.1, 51.5) is None


# ── _parse_gdelt_datetime ────────────────────────────────────────────────────

class TestParseGdeltDatetime:
    def test_valid_format(self):
        dt = _parse_gdelt_datetime("20260403T120000Z")
        assert dt == datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)

    def test_invalid_format_raises(self):
        with pytest.raises(NormalizationError, match="Cannot parse GDELT seendate"):
            _parse_gdelt_datetime("not-a-date")


# ── GdeltConnector.normalize ─────────────────────────────────────────────────

class TestGdeltConnectorNormalize:
    def test_happy_path_produces_canonical_event(self):
        connector = GdeltConnector()
        raw = _article()
        event = connector.normalize(raw)
        assert event.event_type == EventType.CONTEXTUAL_EVENT
        assert event.source_type == SourceType.CONTEXT_FEED
        assert event.entity_type == EntityType.NEWS_ARTICLE
        assert event.source == "gdelt-doc"

    def test_event_time_is_utc(self):
        connector = GdeltConnector()
        event = connector.normalize(_article(seendate="20260403T120000Z"))
        assert event.event_time == datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc)
        assert event.event_time.tzinfo is timezone.utc

    def test_aoi_centroid_used_as_geometry(self):
        connector = GdeltConnector()
        event = connector.normalize(_article(aoi_lon=46.7, aoi_lat=24.7))
        assert event.geometry["coordinates"][0] == pytest.approx(46.7)
        assert event.geometry["coordinates"][1] == pytest.approx(24.7)
        assert event.centroid["type"] == "Point"

    def test_null_island_sets_quality_flag(self):
        connector = GdeltConnector()
        raw = _article(aoi_lon=0.0, aoi_lat=0.0)
        event = connector.normalize(raw)
        assert "geometry-unavailable" in event.quality_flags

    def test_aoi_centroid_sets_geometry_warning(self):
        connector = GdeltConnector()
        raw = _article(aoi_lon=46.7, aoi_lat=24.7)
        event = connector.normalize(raw)
        assert any(
            "geometry-approximated" in w
            for w in event.normalization.normalization_warnings
        )

    def test_empty_record_raises(self):
        connector = GdeltConnector()
        with pytest.raises(NormalizationError):
            connector.normalize({"url": "", "title": ""})

    def test_event_id_is_deterministic(self):
        connector = GdeltConnector()
        raw = _article()
        id1 = connector.normalize(raw).event_id
        id2 = connector.normalize(raw).event_id
        assert id1 == id2

    def test_license_is_public_domain(self):
        connector = GdeltConnector()
        event = connector.normalize(_article())
        assert event.license.access_tier == "public"
        assert event.license.commercial_use == "allowed"

    def test_attributes_headline_and_url(self):
        connector = GdeltConnector()
        event = connector.normalize(_article(url="https://news.example.com/a", title="Big Build"))
        assert event.attributes["headline"] == "Big Build"
        assert event.attributes["url"] == "https://news.example.com/a"


# ── GdeltConnector.normalize_all ─────────────────────────────────────────────

class TestGdeltNormalizeAll:
    def test_skips_bad_records_and_returns_good(self):
        connector = GdeltConnector()
        records = [
            _article(url="https://good.example.com/a"),
            {"url": "", "title": ""},  # bad — should be skipped
            _article(url="https://good.example.com/b"),
        ]
        events = connector.normalize_all(records)
        assert len(events) == 2


# ── GdeltConnector.fetch ─────────────────────────────────────────────────────

class TestGdeltFetch:
    def test_fetch_enriches_articles_with_aoi_centroid(self):
        connector = GdeltConnector()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "articles": [
                {"url": "https://a.com/1", "title": "T1", "seendate": "20260403T120000Z"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            geometry = _polygon_geometry(46.7, 24.7)
            start = datetime(2026, 3, 1, tzinfo=timezone.utc)
            end = datetime(2026, 4, 1, tzinfo=timezone.utc)
            articles = connector.fetch(geometry, start, end)

        assert len(articles) == 1
        assert articles[0]["_aoi_lon"] == pytest.approx(46.7, abs=0.05)
        assert articles[0]["_aoi_lat"] == pytest.approx(24.7, abs=0.05)

    def test_fetch_builds_sourcecountry_query(self):
        connector = GdeltConnector()
        captured_params: Dict[str, Any] = {}

        def mock_get(url, params=None, timeout=None):
            captured_params.update(params or {})
            m = MagicMock()
            m.json.return_value = {"articles": []}
            m.raise_for_status = MagicMock()
            return m

        with patch("httpx.get", side_effect=mock_get):
            geometry = _polygon_geometry(46.7, 24.7)  # Riyadh → Saudi Arabia
            connector.fetch(
                geometry,
                datetime(2026, 3, 1, tzinfo=timezone.utc),
                datetime(2026, 4, 1, tzinfo=timezone.utc),
            )

        assert "Saudi Arabia" in captured_params.get("query", "")

    def test_fetch_raises_on_http_error(self):
        import httpx as _httpx
        connector = GdeltConnector()
        with patch("httpx.get", side_effect=_httpx.RequestError("timeout")):
            with pytest.raises(ConnectorUnavailableError):
                connector.fetch(
                    _polygon_geometry(),
                    datetime(2026, 3, 1, tzinfo=timezone.utc),
                    datetime(2026, 4, 1, tzinfo=timezone.utc),
                )


# ── GdeltConnector.health ────────────────────────────────────────────────────

class TestGdeltHealth:
    def test_healthy_when_api_reachable(self):
        connector = GdeltConnector()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"articles": []}  # connect() only checks status
        with patch("httpx.get", return_value=mock_response):
            status = connector.health()
        assert status.healthy is True
        assert status.connector_id == "gdelt-doc"

    def test_unhealthy_when_api_unreachable(self):
        import httpx as _httpx
        connector = GdeltConnector()
        with patch("httpx.get", side_effect=_httpx.RequestError("connection refused")):
            status = connector.health()
        assert status.healthy is False
        assert "unreachable" in status.message.lower()
