"""Contract tests: verify backend chokepoints and dark-ships API match frontend type expectations.

These tests catch the class of bug where workers/types.py changes break the frontend overlay data.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestChokepointContract:
    def test_chokepoints_response_has_geometry_and_centroid(self, client):
        """Chokepoint must have geometry + centroid, NOT bbox.
        Frontend GlobeView.tsx reads cp.geometry and cp.centroid.lon/lat."""
        response = client.get("/api/v1/chokepoints")
        assert response.status_code == 200
        data = response.json()
        if data.get("chokepoints"):
            cp = data["chokepoints"][0]
            assert "geometry" in cp, "Missing 'geometry' field -- frontend reads cp.geometry"
            assert "centroid" in cp, "Missing 'centroid' field -- frontend reads cp.centroid.lon/lat"
            assert "bbox" not in cp, "'bbox' field present -- frontend does not expect this"
            centroid = cp["centroid"]
            assert "lon" in centroid and "lat" in centroid, "centroid must have lon and lat keys"


class TestDarkShipCandidateContract:
    def test_dark_ship_candidates_have_separate_lon_lat(self, client):
        """DarkShipCandidate must have last_known_lon and last_known_lat as separate fields.
        Frontend GlobeView.tsx reads ds.last_known_lon and ds.last_known_lat."""
        response = client.get("/api/v1/dark-ships")
        assert response.status_code == 200
        data = response.json()
        if data.get("candidates"):
            ds = data["candidates"][0]
            assert "last_known_lon" in ds, "Missing last_known_lon -- frontend reads this directly"
            assert "last_known_lat" in ds, "Missing last_known_lat -- frontend reads this directly"
            assert "last_known_position" not in ds, "'last_known_position' must not exist -- old field name"
