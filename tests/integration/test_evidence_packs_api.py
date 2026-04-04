"""Integration tests for the evidence packs API — Phase 5 Track B."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.services.evidence_pack_service import get_default_evidence_pack_service


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_BASE = "/api/v1/evidence-packs"
_INV_BASE = "/api/v1/investigations"


@pytest.fixture(autouse=True)
def _clear_packs():
    """Isolate each test by clearing the in-memory pack store."""
    svc = get_default_evidence_pack_service()
    svc.clear()
    yield
    svc.clear()


def _make_pack(client: TestClient, **overrides) -> dict:
    payload = {"title": "Test Pack", **overrides}
    resp = client.post(_BASE, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ──────────────────────────────────────────────────────────────────────────────
# 1. POST / generates pack (201)
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_pack_returns_201(app_client):
    resp = app_client.post(_BASE, json={"title": "Initial Pack"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Initial Pack"
    assert "pack_id" in data
    assert data["total_events"] == 0
    assert data["export_format"] == "json"


# ──────────────────────────────────────────────────────────────────────────────
# 2. GET / returns list
# ──────────────────────────────────────────────────────────────────────────────

def test_list_packs(app_client):
    _make_pack(app_client, title="Pack A")
    _make_pack(app_client, title="Pack B")
    resp = app_client.get(_BASE)
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == 2


# ──────────────────────────────────────────────────────────────────────────────
# 3. GET /{id} returns pack
# ──────────────────────────────────────────────────────────────────────────────

def test_get_pack(app_client):
    created = _make_pack(app_client, title="Lookup Pack")
    pack_id = created["pack_id"]
    resp = app_client.get(f"{_BASE}/{pack_id}")
    assert resp.status_code == 200
    assert resp.json()["pack_id"] == pack_id
    assert resp.json()["title"] == "Lookup Pack"


# ──────────────────────────────────────────────────────────────────────────────
# 4. GET /{id} returns 404 for missing
# ──────────────────────────────────────────────────────────────────────────────

def test_get_missing_pack_404(app_client):
    resp = app_client.get(f"{_BASE}/nonexistent-id")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 5. DELETE /{id} returns 204
# ──────────────────────────────────────────────────────────────────────────────

def test_delete_pack_204(app_client):
    created = _make_pack(app_client)
    pack_id = created["pack_id"]
    resp = app_client.delete(f"{_BASE}/{pack_id}")
    assert resp.status_code == 204
    # Confirm it's gone
    assert app_client.get(f"{_BASE}/{pack_id}").status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 6. GET /{id}/download with format=json returns bytes
# ──────────────────────────────────────────────────────────────────────────────

def test_download_pack_json(app_client):
    created = _make_pack(app_client, title="JSON Download")
    pack_id = created["pack_id"]
    resp = app_client.get(f"{_BASE}/{pack_id}/download?format=json", follow_redirects=True)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    parsed = json.loads(resp.content)
    assert parsed["title"] == "JSON Download"


# ──────────────────────────────────────────────────────────────────────────────
# 7. GET /{id}/download with format=markdown returns text
# ──────────────────────────────────────────────────────────────────────────────

def test_download_pack_markdown(app_client):
    created = _make_pack(app_client, title="Markdown Export")
    pack_id = created["pack_id"]
    resp = app_client.get(f"{_BASE}/{pack_id}/download?format=markdown")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    text = resp.content.decode("utf-8")
    assert "# Evidence Pack: Markdown Export" in text
    assert "## Timeline" in text


# ──────────────────────────────────────────────────────────────────────────────
# 8. GET /{id}/download with format=geojson returns GeoJSON bytes
# ──────────────────────────────────────────────────────────────────────────────

def test_download_pack_geojson(app_client):
    created = _make_pack(app_client, title="GeoJSON Export")
    pack_id = created["pack_id"]
    resp = app_client.get(f"{_BASE}/{pack_id}/download?format=geojson")
    assert resp.status_code == 200
    assert "geo+json" in resp.headers["content-type"]
    parsed = json.loads(resp.content)
    assert parsed["type"] == "FeatureCollection"
    assert "features" in parsed


# ──────────────────────────────────────────────────────────────────────────────
# 9. GET / ?investigation_id= filters results
# ──────────────────────────────────────────────────────────────────────────────

def test_list_packs_filter_by_investigation(app_client):
    _make_pack(app_client, title="Pack No Inv")
    _make_pack(app_client, title="Pack With Inv", investigation_id="inv-999")
    resp = app_client.get(f"{_BASE}?investigation_id=inv-999")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["investigation_id"] == "inv-999"


# ──────────────────────────────────────────────────────────────────────────────
# 10. POST /from-investigation/{inv_id} generates pack from investigation
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_from_investigation(app_client):
    # Create an investigation first
    inv_resp = app_client.post(
        _INV_BASE,
        json={"name": "Test Investigation", "description": "For evidence pack test"},
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    resp = app_client.post(f"{_BASE}/from-investigation/{inv_id}")
    assert resp.status_code == 201
    data = resp.json()
    assert data["investigation_id"] == inv_id
    assert "Test Investigation" in data["title"]


# ──────────────────────────────────────────────────────────────────────────────
# 11. POST /from-investigation/{inv_id} returns 404 for missing investigation
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_from_missing_investigation_404(app_client):
    resp = app_client.post(f"{_BASE}/from-investigation/no-such-investigation")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 12. DELETE on missing pack returns 404
# ──────────────────────────────────────────────────────────────────────────────

def test_delete_missing_pack_404(app_client):
    resp = app_client.delete(f"{_BASE}/not-a-real-id")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 13. POST / with explicit description stored correctly
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_pack_stores_description(app_client):
    resp = app_client.post(
        _BASE,
        json={"title": "Described Pack", "description": "Important context"},
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "Important context"


# ──────────────────────────────────────────────────────────────────────────────
# 14. POST / with export_format=markdown preserved in stored pack
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_pack_stores_export_format(app_client):
    resp = app_client.post(
        _BASE,
        json={"title": "Markdown Pack", "export_format": "markdown"},
    )
    assert resp.status_code == 201
    assert resp.json()["export_format"] == "markdown"
