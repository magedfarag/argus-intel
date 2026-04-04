"""Unit tests for V2 STAC Imagery connectors (P1-3.10 — ≥15 tests).

Tests cover:
- stac_normalizer.stac_item_to_canonical_event() happy path and error cases
- CdseSentinel2Connector normalization (P1-3.1)
- UsgsLandsatConnector normalization (P1-3.2)
- EarthSearchConnector normalization (P1-3.3)
- PlanetaryComputerConnector normalization (P1-3.4)
- POST /api/v1/imagery/search endpoint with mocked connectors
- GET  /api/v1/imagery/providers endpoint
- ImagerySearchRequest validation
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.connectors.base import ConnectorHealthStatus, ConnectorUnavailableError
from src.connectors.earth_search import EarthSearchConnector
from src.connectors.landsat import UsgsLandsatConnector
from src.connectors.planetary_computer import PlanetaryComputerConnector
from src.connectors.registry import ConnectorRegistry
from src.connectors.sentinel2 import CdseSentinel2Connector
from src.connectors.stac_normalizer import (
    _centroid_from_geometry,
    _geometry_from_item,
    stac_item_to_canonical_event,
)
from src.models.canonical_event import EventType, SourceType
from src.models.imagery import ImagerySearchRequest


# ── Shared STAC item fixtures ─────────────────────────────────────────────────

def _minimal_stac_item(item_id: str = "S2A_TEST", cloud: float = 5.0) -> Dict[str, Any]:
    return {
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [46.5, 24.6], [46.8, 24.6], [46.8, 24.9], [46.5, 24.9], [46.5, 24.6],
            ]],
        },
        "bbox": [46.5, 24.6, 46.8, 24.9],
        "properties": {
            "datetime": "2026-03-15T08:30:00Z",
            "eo:cloud_cover": cloud,
            "platform": "sentinel-2a",
            "gsd": 10.0,
            "processing:level": "L2A",
        },
        "assets": {
            "B04": {"href": "https://example.com/B04.tif"},
            "B08": {"href": "https://example.com/B08.tif"},
            "thumbnail": {"href": "https://example.com/thumb.png"},
        },
        "links": [{"rel": "self", "href": "https://catalog.example.com/S2A_TEST"}],
    }


def _landsat_item() -> Dict[str, Any]:
    return {
        "id": "LC09_L2SP_166040_20260310",
        "collection": "landsat-c2-l2",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0],
            ]],
        },
        "bbox": [46.0, 24.0, 47.0, 25.0],
        "properties": {
            "datetime": "2026-03-10T07:15:00Z",
            "eo:cloud_cover": 12.0,
            "platform": "LANDSAT_9",
            "gsd": 30.0,
            "processing:level": "L2",
        },
        "assets": {
            "SR_B4": {"href": "https://example.com/B4.tif"},
            "SR_B5": {"href": "https://example.com/B5.tif"},
        },
        "links": [],
    }


# ── stac_normalizer tests ─────────────────────────────────────────────────────

class TestStacNormalizer:
    def test_happy_path_produces_canonical_event(self):
        item = _minimal_stac_item()
        event = stac_item_to_canonical_event(item, "test-connector", "test-src")
        assert event.event_type == EventType.IMAGERY_ACQUISITION
        assert event.source_type == SourceType.IMAGERY_CATALOG
        assert event.entity_id == "S2A_TEST"
        assert event.event_time == datetime(2026, 3, 15, 8, 30, 0, tzinfo=timezone.utc)

    def test_event_id_is_deterministic(self):
        item = _minimal_stac_item()
        id1 = stac_item_to_canonical_event(item, "c1", "s1").event_id
        id2 = stac_item_to_canonical_event(item, "c1", "s1").event_id
        assert id1 == id2

    def test_cloud_cover_mapped_to_attributes(self):
        item = _minimal_stac_item(cloud=8.5)
        event = stac_item_to_canonical_event(item, "c", "s")
        assert event.attributes["cloud_cover_pct"] == pytest.approx(8.5)

    def test_quality_flag_set_for_high_cloud(self):
        item = _minimal_stac_item(cloud=30.0)
        event = stac_item_to_canonical_event(item, "c", "s")
        assert "cloud-filtered" in event.quality_flags

    def test_no_quality_flag_for_low_cloud(self):
        item = _minimal_stac_item(cloud=5.0)
        event = stac_item_to_canonical_event(item, "c", "s")
        assert "cloud-filtered" not in event.quality_flags

    def test_missing_id_raises_normalization_error(self):
        from src.connectors.base import NormalizationError
        item = _minimal_stac_item()
        del item["id"]
        with pytest.raises(NormalizationError):
            stac_item_to_canonical_event(item, "c", "s")

    def test_missing_datetime_raises_normalization_error(self):
        from src.connectors.base import NormalizationError
        item = _minimal_stac_item()
        del item["properties"]["datetime"]
        with pytest.raises(NormalizationError):
            stac_item_to_canonical_event(item, "c", "s")

    def test_geometry_from_bbox_fallback(self):
        item = _minimal_stac_item()
        item["geometry"] = None
        event = stac_item_to_canonical_event(item, "c", "s")
        assert event.geometry["type"] == "Polygon"

    def test_centroid_computed_from_polygon(self):
        poly = {
            "type": "Polygon",
            "coordinates": [[
                [0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0],
            ]],
        }
        centroid = _centroid_from_geometry(poly)
        assert centroid["type"] == "Point"
        assert centroid["coordinates"][0] == pytest.approx(0.8, abs=0.5)

    def test_platform_extracted(self):
        item = _minimal_stac_item()
        event = stac_item_to_canonical_event(item, "c", "s")
        assert event.attributes.get("platform") == "sentinel-2a"

    def test_gsd_extracted(self):
        item = _minimal_stac_item()
        event = stac_item_to_canonical_event(item, "c", "s")
        assert event.attributes.get("gsd_m") == pytest.approx(10.0)


# ── Connector normalize() tests ───────────────────────────────────────────────

class TestCdseSentinel2Connector:
    def test_normalize_produces_cdse_source(self):
        connector = CdseSentinel2Connector()
        event = connector.normalize(_minimal_stac_item())
        assert event.source == "copernicus-cdse"
        assert event.event_type == EventType.IMAGERY_ACQUISITION

    def test_connector_id(self):
        assert CdseSentinel2Connector.connector_id == "cdse-sentinel2"
        assert CdseSentinel2Connector.source_type == "imagery_catalog"


class TestUsgsLandsatConnector:
    def test_normalize_produces_usgs_source(self):
        connector = UsgsLandsatConnector()
        event = connector.normalize(_landsat_item())
        assert event.source == "usgs-landsat"

    def test_connector_id(self):
        assert UsgsLandsatConnector.connector_id == "usgs-landsat"


class TestEarthSearchConnector:
    def test_normalize_includes_collection_in_source(self):
        connector = EarthSearchConnector()
        item = _minimal_stac_item()
        item["collection"] = "sentinel-2-l2a"
        event = connector.normalize(item)
        assert "earth-search" in event.source
        assert "sentinel-2-l2a" in event.source

    def test_normalize_fallback_source_without_collection(self):
        connector = EarthSearchConnector()
        item = _minimal_stac_item()
        item.pop("collection", None)
        event = connector.normalize(item)
        assert event.source == "earth-search"


class TestPlanetaryComputerConnector:
    def test_normalize_includes_collection(self):
        connector = PlanetaryComputerConnector()
        item = _minimal_stac_item()
        item["collection"] = "sentinel-2-l2a"
        event = connector.normalize(item)
        assert "planetary-computer" in event.source

    def test_subscription_key_injected_into_headers(self):
        connector = PlanetaryComputerConnector(subscription_key="test-key")
        headers = connector._request_headers()
        assert headers["Ocp-Apim-Subscription-Key"] == "test-key"

    def test_no_subscription_key_no_auth_header(self):
        connector = PlanetaryComputerConnector(subscription_key="")
        headers = connector._request_headers()
        assert "Ocp-Apim-Subscription-Key" not in headers


# ── Imagery router tests ──────────────────────────────────────────────────────

def _make_mock_connector(
    cid: str,
    display: str,
    items: List[Dict[str, Any]],
    *,
    fail: bool = False,
) -> MagicMock:
    """Factory for a minimal mock connector that returns preset items."""
    mock = MagicMock()
    mock.connector_id = cid
    mock.display_name = display
    mock.source_type = "imagery_catalog"
    mock._collections = ["sentinel-2-l2a"]
    mock._needs_auth = False

    if fail:
        mock.fetch_and_normalize.side_effect = ConnectorUnavailableError("test error")
    else:
        from src.connectors.stac_normalizer import stac_item_to_canonical_event
        events = [stac_item_to_canonical_event(i, cid, cid) for i in items]
        mock.fetch_and_normalize.return_value = (events, [])
        health = ConnectorHealthStatus(connector_id=cid, healthy=True, message="ok")
        mock.health.return_value = health

    return mock


@pytest.fixture
def imagery_client():
    from src.api.imagery import router, set_connector_registry, _connector_registry

    registry = ConnectorRegistry()
    mock_connector = _make_mock_connector(
        "earth-search", "Earth Search", [_minimal_stac_item("A"), _minimal_stac_item("B")]
    )
    registry._connectors["earth-search"] = mock_connector

    set_connector_registry(registry)

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)

    # Restore original state
    import src.api.imagery as imagery_mod
    imagery_mod._connector_registry = None


class TestImagerySearchEndpoint:
    _body = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[46.5, 24.6], [46.8, 24.6], [46.8, 24.9], [46.5, 24.9], [46.5, 24.6]]],
        },
        "start_time": "2026-03-01T00:00:00Z",
        "end_time": "2026-03-31T23:59:59Z",
        "cloud_threshold": 20.0,
        "max_results": 10,
    }

    def test_search_returns_200_with_items(self, imagery_client):
        resp = imagery_client.post("/api/v1/imagery/search", json=self._body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_items"] == 2
        assert len(data["items"]) == 2

    def test_search_returns_connector_summaries(self, imagery_client):
        resp = imagery_client.post("/api/v1/imagery/search", json=self._body)
        summaries = resp.json()["connector_summaries"]
        assert any(s["connector_id"] == "earth-search" for s in summaries)

    def test_search_invalid_geometry_type_returns_422(self, imagery_client):
        bad = dict(self._body)
        bad["geometry"] = {"type": "Point", "coordinates": [46.6, 24.7]}
        resp = imagery_client.post("/api/v1/imagery/search", json=bad)
        assert resp.status_code == 422

    def test_search_with_connector_filter(self, imagery_client):
        body = dict(self._body)
        body["connectors"] = ["earth-search"]
        resp = imagery_client.post("/api/v1/imagery/search", json=body)
        assert resp.status_code == 200

    def test_search_empty_when_no_connectors_registered(self):
        from src.api.imagery import router, set_connector_registry
        set_connector_registry(ConnectorRegistry())  # empty
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/v1/imagery/search", json=self._body)
        assert resp.status_code == 200
        assert resp.json()["total_items"] == 0

    def test_search_connector_error_logged_as_summary(self):
        from src.api.imagery import router, set_connector_registry
        registry = ConnectorRegistry()
        failing = _make_mock_connector("bad-connector", "Bad", [], fail=True)
        registry._connectors["bad-connector"] = failing
        set_connector_registry(registry)

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/v1/imagery/search", json=self._body)
        assert resp.status_code == 200
        summaries = resp.json()["connector_summaries"]
        assert summaries[0]["error"] is not None


class TestImageryProvidersEndpoint:
    def test_providers_returns_200(self, imagery_client):
        resp = imagery_client.get("/api/v1/imagery/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "total" in data

    def test_providers_includes_registered_connectors(self, imagery_client):
        resp = imagery_client.get("/api/v1/imagery/providers")
        ids = [p["connector_id"] for p in resp.json()["providers"]]
        assert "earth-search" in ids


class TestGetImageryItemEndpoint:
    def test_get_item_returns_501_pending_postgis(self, imagery_client):
        resp = imagery_client.get("/api/v1/imagery/items/some-event-id")
        assert resp.status_code == 501
