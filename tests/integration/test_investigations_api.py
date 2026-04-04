"""Integration tests for the Investigations API — Phase 5 Track A.

Uses FastAPI TestClient via the shared app_client fixture from conftest.py.
Each test class clears the investigation store before running to avoid
cross-test pollution.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.services.investigation_service import get_default_investigation_store


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


BASE = "/api/v1/investigations"


def _create(client: TestClient, **kwargs) -> dict:
    payload = {"name": "Op Nightwatch", **kwargs}
    r = client.post(BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(autouse=True)
def _clear_store():
    """Wipe the investigation store before every test."""
    get_default_investigation_store().clear()
    yield
    get_default_investigation_store().clear()


# ──────────────────────────────────────────────────────────────────────────────
# 1. POST / — create investigation
# ──────────────────────────────────────────────────────────────────────────────


def test_create_returns_201(app_client: TestClient):
    r = app_client.post(BASE, json={"name": "Test Inv"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Test Inv"
    assert data["status"] == "draft"
    assert "id" in data


def test_create_with_all_fields(app_client: TestClient):
    r = app_client.post(
        BASE,
        json={
            "name": "Full Inv",
            "description": "Narrows traffic analysis",
            "created_by": "analyst-1",
            "tags": ["maritime", "chokepoint"],
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["description"] == "Narrows traffic analysis"
    assert "maritime" in data["tags"]


def test_create_assigns_unique_ids(app_client: TestClient):
    a = _create(app_client, name="A")
    b = _create(app_client, name="B")
    assert a["id"] != b["id"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. GET / — list investigations
# ──────────────────────────────────────────────────────────────────────────────


def test_list_returns_empty(app_client: TestClient):
    r = app_client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_returns_created_item(app_client: TestClient):
    _create(app_client)
    r = app_client.get(BASE)
    data = r.json()
    assert data["total"] == 1


def test_list_status_filter(app_client: TestClient):
    inv = _create(app_client)
    # Update to active
    app_client.put(f"{BASE}/{inv['id']}", json={"status": "active"})
    _create(app_client, name="Draft One")

    r = app_client.get(BASE, params={"status": "active"})
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "active"


# ──────────────────────────────────────────────────────────────────────────────
# 3. GET /{id} — get single
# ──────────────────────────────────────────────────────────────────────────────


def test_get_existing(app_client: TestClient):
    inv = _create(app_client)
    r = app_client.get(f"{BASE}/{inv['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == inv["id"]


def test_get_missing_returns_404(app_client: TestClient):
    r = app_client.get(f"{BASE}/nonexistent-id")
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 4. PUT /{id} — update
# ──────────────────────────────────────────────────────────────────────────────


def test_update_name(app_client: TestClient):
    inv = _create(app_client)
    r = app_client.put(f"{BASE}/{inv['id']}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_update_status(app_client: TestClient):
    inv = _create(app_client)
    r = app_client.put(f"{BASE}/{inv['id']}", json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_update_missing_returns_404(app_client: TestClient):
    r = app_client.put(f"{BASE}/missing", json={"name": "X"})
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 5. DELETE /{id} — delete
# ──────────────────────────────────────────────────────────────────────────────


def test_delete_returns_204(app_client: TestClient):
    inv = _create(app_client)
    r = app_client.delete(f"{BASE}/{inv['id']}")
    assert r.status_code == 204


def test_delete_removes_from_list(app_client: TestClient):
    inv = _create(app_client)
    app_client.delete(f"{BASE}/{inv['id']}")
    r = app_client.get(BASE)
    assert r.json()["total"] == 0


def test_delete_missing_returns_404(app_client: TestClient):
    r = app_client.delete(f"{BASE}/missing")
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 6. POST /{id}/notes — add note
# ──────────────────────────────────────────────────────────────────────────────


def test_add_note(app_client: TestClient):
    inv = _create(app_client)
    note = {
        "investigation_id": inv["id"],
        "content": "Initial AIS gap detected.",
        "author": "analyst-2",
        "tags": ["ais", "gap"],
    }
    r = app_client.post(f"{BASE}/{inv['id']}/notes", json=note)
    assert r.status_code == 201
    data = r.json()
    assert len(data["notes"]) == 1
    assert data["notes"][0]["content"] == "Initial AIS gap detected."


def test_add_note_missing_investigation(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/missing/notes",
        json={"investigation_id": "missing", "content": "test"},
    )
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 7. POST /{id}/watchlist — add watchlist entry
# ──────────────────────────────────────────────────────────────────────────────


def test_add_watchlist_entry(app_client: TestClient):
    inv = _create(app_client)
    entry = {"entry_type": "vessel", "identifier": "123456789", "label": "MV Atlas"}
    r = app_client.post(f"{BASE}/{inv['id']}/watchlist", json=entry)
    assert r.status_code == 201
    data = r.json()
    assert len(data["watchlist"]) == 1
    assert data["watchlist"][0]["identifier"] == "123456789"


def test_add_watchlist_missing_investigation(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/missing/watchlist",
        json={"entry_type": "vessel", "identifier": "x"},
    )
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 8. POST /{id}/evidence — add evidence link (idempotent)
# ──────────────────────────────────────────────────────────────────────────────


def test_add_evidence_link(app_client: TestClient):
    inv = _create(app_client)
    link = {
        "evidence_id": "ev-001",
        "event_id": "canonical-001",
        "evidence_type": "imagery",
        "description": "Sentinel-2 overpass",
    }
    r = app_client.post(f"{BASE}/{inv['id']}/evidence", json=link)
    assert r.status_code == 201
    data = r.json()
    assert len(data["evidence_links"]) == 1
    assert data["evidence_links"][0]["evidence_id"] == "ev-001"


def test_add_evidence_link_is_idempotent(app_client: TestClient):
    inv = _create(app_client)
    link = {
        "evidence_id": "ev-001",
        "event_id": "canonical-001",
        "evidence_type": "imagery",
    }
    app_client.post(f"{BASE}/{inv['id']}/evidence", json=link)
    r = app_client.post(f"{BASE}/{inv['id']}/evidence", json=link)
    assert r.status_code == 201
    data = r.json()
    # Still only one link despite two POST requests
    assert len(data["evidence_links"]) == 1


def test_add_evidence_link_missing_investigation(app_client: TestClient):
    r = app_client.post(
        f"{BASE}/missing/evidence",
        json={"evidence_id": "e", "event_id": "ev", "evidence_type": "imagery"},
    )
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 9. POST /{id}/filters — save filter
# ──────────────────────────────────────────────────────────────────────────────


def test_add_saved_filter(app_client: TestClient):
    inv = _create(app_client)
    filt = {
        "name": "Dark ship candidates",
        "filter_definition": {"event_types": ["dark_ship_candidate"]},
    }
    r = app_client.post(f"{BASE}/{inv['id']}/filters", json=filt)
    assert r.status_code == 201
    data = r.json()
    assert len(data["saved_filters"]) == 1
    assert data["saved_filters"][0]["name"] == "Dark ship candidates"


# ──────────────────────────────────────────────────────────────────────────────
# 10. GET /{id}/export — JSON export
# ──────────────────────────────────────────────────────────────────────────────


def test_export_returns_full_investigation(app_client: TestClient):
    inv = _create(app_client, description="Export test", tags=["export"])
    r = app_client.get(f"{BASE}/{inv['id']}/export")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == inv["id"]
    assert data["description"] == "Export test"
    assert "export" in data["tags"]


def test_export_missing_returns_404(app_client: TestClient):
    r = app_client.get(f"{BASE}/missing/export")
    assert r.status_code == 404
