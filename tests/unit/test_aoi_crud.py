"""Unit tests for AOI CRUD service and router (P1-2.6 — ≥12 tests)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.aois import router as aoi_router, _store
from src.models.aoi import AOICreate, AOIUpdate, GeometryModel
from src.services.aoi_store import AOIStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def _polygon_geometry() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[46.5, 24.6], [46.8, 24.6], [46.8, 24.9], [46.5, 24.9], [46.5, 24.6]]],
    }


def _create_payload(name: str = "Riyadh AOI") -> dict:
    return {"name": name, "geometry": _polygon_geometry(), "tags": ["pilot"]}


@pytest.fixture(autouse=True)
def reset_store():
    """Clear singleton store between tests."""
    from src.api.aois import _store
    _store._store.clear()
    yield
    _store._store.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(aoi_router)
    return TestClient(app)


# ── AOIStore unit tests ───────────────────────────────────────────────────────

class TestAOIStore:
    def test_create_returns_aoi_with_id(self):
        store = AOIStore()
        payload = AOICreate(name="Dubai", geometry=GeometryModel(**_polygon_geometry()))
        aoi = store.create(payload)
        assert aoi.id
        assert aoi.name == "Dubai"
        assert not aoi.deleted

    def test_get_returns_none_for_unknown_id(self):
        store = AOIStore()
        assert store.get("nonexistent") is None

    def test_get_returns_created_aoi(self):
        store = AOIStore()
        payload = AOICreate(name="Doha", geometry=GeometryModel(**_polygon_geometry()))
        created = store.create(payload)
        fetched = store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_soft_delete_removes_from_active_list(self):
        store = AOIStore()
        payload = AOICreate(name="Abu Dhabi", geometry=GeometryModel(**_polygon_geometry()))
        aoi = store.create(payload)
        assert store.soft_delete(aoi.id)
        assert store.get(aoi.id) is None
        assert store.count_active() == 0

    def test_soft_delete_unknown_id_returns_false(self):
        store = AOIStore()
        assert not store.soft_delete("no-such-id")

    def test_update_modifies_name(self):
        store = AOIStore()
        payload = AOICreate(name="Old Name", geometry=GeometryModel(**_polygon_geometry()))
        aoi = store.create(payload)
        updated = store.update(aoi.id, AOIUpdate(name="New Name"))
        assert updated is not None
        assert updated.name == "New Name"

    def test_update_nonexistent_returns_none(self):
        store = AOIStore()
        result = store.update("fake-id", AOIUpdate(name="X"))
        assert result is None

    def test_list_active_pagination(self):
        store = AOIStore()
        for i in range(5):
            store.create(AOICreate(name=f"AOI-{i}", geometry=GeometryModel(**_polygon_geometry())))
        page1 = store.list_active(page=1, page_size=3)
        page2 = store.list_active(page=2, page_size=3)
        assert len(page1) == 3
        assert len(page2) == 2


# ── FastAPI router tests ──────────────────────────────────────────────────────

class TestAOIRouter:
    def test_post_creates_aoi_and_returns_201(self, client):
        resp = client.post("/api/v1/aois", json=_create_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Riyadh AOI"

    def test_get_all_returns_empty_list_initially(self, client):
        resp = client.get("/api/v1/aois")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_get_by_id_returns_created_aoi(self, client):
        created = client.post("/api/v1/aois", json=_create_payload()).json()
        resp = client.get(f"/api/v1/aois/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_unknown_id_returns_404(self, client):
        resp = client.get("/api/v1/aois/no-such-id")
        assert resp.status_code == 404

    def test_delete_removes_aoi(self, client):
        created = client.post("/api/v1/aois", json=_create_payload()).json()
        del_resp = client.delete(f"/api/v1/aois/{created['id']}")
        assert del_resp.status_code == 204
        assert client.get(f"/api/v1/aois/{created['id']}").status_code == 404

    def test_put_updates_aoi_name(self, client):
        created = client.post("/api/v1/aois", json=_create_payload()).json()
        resp = client.put(f"/api/v1/aois/{created['id']}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_geometry_type_not_polygon_rejected(self, client):
        payload = {"name": "Bad Geo", "geometry": {"type": "Point", "coordinates": [46.5, 24.6]}}
        resp = client.post("/api/v1/aois", json=payload)
        assert resp.status_code == 422
