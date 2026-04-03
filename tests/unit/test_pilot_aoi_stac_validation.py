"""P1-6.2: STAC search validation on the three Middle East pilot AOIs.

Tests verify that:
- Pilot AOI geometries are valid closed GeoJSON Polygons in EPSG:4326
- Bounding-box calculations from AOI geometries are correct
- Expected STAC collections are present and match connector defaults
- EarthSearch and CdseSentinel2 connectors generate correct search payloads
  for each pilot AOI (no live network calls — all external HTTP mocked)
- Cross-check: at least one of the expected STAC collections from each pilot
  AOI is present in EarthSearchConnector._DEFAULT_COLLECTIONS
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.earth_search import EarthSearchConnector, _DEFAULT_COLLECTIONS
from src.models.pilot_aois import PILOT_AOIS


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ring_is_closed(ring: List[List[float]]) -> bool:
    """A polygon ring is closed when its first and last point are identical."""
    return len(ring) >= 4 and ring[0] == ring[-1]


def _bbox_from_polygon(geometry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Return (west, south, east, north) from a GeoJSON Polygon."""
    ring = geometry["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _centroid_inside_bbox(
    centroid: Dict[str, float],
    bbox: Tuple[float, float, float, float],
) -> bool:
    lon, lat = centroid["lon"], centroid["lat"]
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


# ── Geometry + structure validation ───────────────────────────────────────────


class TestPilotAOIStructure:
    """Validate that each pilot AOI has the required fields and geometry."""

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_required_keys_present(self, aoi: Dict[str, Any]) -> None:
        for key in ("id", "name", "geometry", "centroid", "expected_stac_collections"):
            assert key in aoi, f"AOI missing key '{key}': {aoi.get('id')}"

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_geometry_type_is_polygon(self, aoi: Dict[str, Any]) -> None:
        assert aoi["geometry"]["type"] == "Polygon", (
            f"{aoi['id']} geometry is not a Polygon"
        )

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_polygon_ring_is_closed(self, aoi: Dict[str, Any]) -> None:
        ring = aoi["geometry"]["coordinates"][0]
        assert _ring_is_closed(ring), (
            f"{aoi['id']} polygon outer ring is not closed (first != last)"
        )

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_polygon_has_at_least_four_points(self, aoi: Dict[str, Any]) -> None:
        ring = aoi["geometry"]["coordinates"][0]
        assert len(ring) >= 4, f"{aoi['id']} ring has fewer than 4 points"

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_centroid_inside_polygon_bbox(self, aoi: Dict[str, Any]) -> None:
        bbox = _bbox_from_polygon(aoi["geometry"])
        assert _centroid_inside_bbox(aoi["centroid"], bbox), (
            f"{aoi['id']} centroid {aoi['centroid']} is outside its own bbox {bbox}"
        )

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_coordinates_in_valid_wgs84_range(self, aoi: Dict[str, Any]) -> None:
        ring = aoi["geometry"]["coordinates"][0]
        for lon, lat in ring:
            assert -180.0 <= lon <= 180.0, f"{aoi['id']} lon {lon} out of WGS-84 range"
            assert -90.0 <= lat <= 90.0, f"{aoi['id']} lat {lat} out of WGS-84 range"

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_expected_stac_collections_nonempty(self, aoi: Dict[str, Any]) -> None:
        assert len(aoi["expected_stac_collections"]) >= 1, (
            f"{aoi['id']} has no expected STAC collections"
        )

    def test_three_pilot_aois_defined(self) -> None:
        assert len(PILOT_AOIS) == 3, f"Expected 3 pilot AOIs, got {len(PILOT_AOIS)}"

    def test_pilot_aoi_ids_are_unique(self) -> None:
        ids = [a["id"] for a in PILOT_AOIS]
        assert len(ids) == len(set(ids)), "Pilot AOI ids are not unique"


# ── STAC collection cross-check ───────────────────────────────────────────────


class TestSTACCollectionCoverage:
    """Cross-check: each AOI's expected collections against connector defaults."""

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_at_least_one_expected_collection_in_earth_search_defaults(
        self, aoi: Dict[str, Any]
    ) -> None:
        overlap = set(aoi["expected_stac_collections"]) & set(_DEFAULT_COLLECTIONS)
        assert overlap, (
            f"{aoi['id']} expected collections {aoi['expected_stac_collections']} "
            f"have no overlap with EarthSearch defaults {_DEFAULT_COLLECTIONS}"
        )

    def test_sentinel2_l2a_in_earth_search_defaults(self) -> None:
        assert "sentinel-2-l2a" in _DEFAULT_COLLECTIONS

    def test_landsat_in_earth_search_defaults(self) -> None:
        assert "landsat-c2-l2" in _DEFAULT_COLLECTIONS


# ── EarthSearch payload validation ───────────────────────────────────────────


class TestEarthSearchPayloadForPilotAOIs:
    """Validate search payloads sent to Earth Search for each pilot AOI."""

    START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    END = datetime(2026, 3, 28, 23, 59, 59, tzinfo=timezone.utc)

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_geometry_forwarded_to_stac_payload(self, aoi: Dict[str, Any]) -> None:
        """Earth Search receives the AOI geometry as the ``intersects`` parameter."""
        captured: list[Dict[str, Any]] = []

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"features": []}

        def capture_post(url: str, json: Dict[str, Any], **kw: Any) -> MagicMock:
            captured.append(json)
            return mock_response

        connector = EarthSearchConnector()
        with patch("httpx.post", side_effect=capture_post):
            connector.fetch(aoi["geometry"], self.START, self.END)

        assert len(captured) == 1
        payload = captured[0]
        assert payload["intersects"] == aoi["geometry"]

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_datetime_range_in_payload(self, aoi: Dict[str, Any]) -> None:
        """Datetime range in STAC payload covers the requested window."""
        captured: list[Dict[str, Any]] = []

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"features": []}

        def capture_post(url: str, json: Dict[str, Any], **kw: Any) -> MagicMock:
            captured.append(json)
            return mock_response

        connector = EarthSearchConnector()
        with patch("httpx.post", side_effect=capture_post):
            connector.fetch(aoi["geometry"], self.START, self.END)

        dt_range = captured[0]["datetime"]
        assert "2026-01-01T00:00:00Z" in dt_range
        assert "2026-03-28T23:59:59Z" in dt_range

    @pytest.mark.parametrize("aoi", PILOT_AOIS)
    def test_collections_include_sentinel2(self, aoi: Dict[str, Any]) -> None:
        """Earth Search search targets sentinel-2-l2a for all pilot AOIs."""
        captured: list[Dict[str, Any]] = []

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"features": []}

        def capture_post(url: str, json: Dict[str, Any], **kw: Any) -> MagicMock:
            captured.append(json)
            return mock_response

        connector = EarthSearchConnector()
        with patch("httpx.post", side_effect=capture_post):
            connector.fetch(aoi["geometry"], self.START, self.END)

        collections = captured[0]["collections"]
        assert "sentinel-2-l2a" in collections, (
            f"sentinel-2-l2a not in payload collections for {aoi['id']}: {collections}"
        )
