"""Integration tests for the Analyst Query and Briefing API — Phase 5 Track C.

Uses FastAPI TestClient via the shared app_client fixture from conftest.py.
Each test resets the analyst query service to avoid cross-test pollution.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import src.services.analyst_query_service as _svc_mod
from src.models.analyst_query import (
    AnalystQuery,
    BriefingRequest,
    BriefingSection,
    QueryFieldType,
    QueryFilter,
)
from src.services.analyst_query_service import AnalystQueryService


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

BASE = "/api/v1/analyst"
_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_service():
    """Replace the global singleton with a fresh instance before every test."""
    fresh = AnalystQueryService()
    _svc_mod._default_service = fresh
    yield
    _svc_mod._default_service = fresh  # leave clean for GC


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Query surface
# ──────────────────────────────────────────────────────────────────────────────


def test_post_query_returns_query_result(app_client: TestClient):
    """POST /analyst/query executes an ad-hoc query and returns QueryResult."""
    payload = {
        "query_id": "11111111-1111-1111-1111-111111111111",
        "filters": [],
        "combine_with": "and",
        "limit": 10,
    }
    resp = app_client.post(f"{BASE}/query", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "query_id" in data
    assert "total_matched" in data
    assert "returned_count" in data
    assert "events" in data
    assert "sources_cited" in data


def test_post_query_does_not_save(app_client: TestClient):
    """POST /analyst/query does NOT save the query."""
    payload = {
        "query_id": "22222222-2222-2222-2222-222222222222",
        "filters": [],
    }
    app_client.post(f"{BASE}/query", json=payload)
    # Saved queries list must remain empty
    resp = app_client.get(f"{BASE}/queries")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_queries_saves_query(app_client: TestClient):
    """POST /analyst/queries saves a query and returns it."""
    payload = {
        "label": "Vessel Filter",
        "filters": [
            {"field": "event_type", "operator": "eq", "value": "ship_position"}
        ],
    }
    resp = app_client.post(f"{BASE}/queries", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "Vessel Filter"
    assert "query_id" in data


def test_get_queries_returns_saved(app_client: TestClient):
    """GET /analyst/queries returns list of saved queries."""
    # Save two queries
    for label in ("Alpha", "Beta"):
        app_client.post(f"{BASE}/queries", json={"label": label, "filters": []})
    resp = app_client.get(f"{BASE}/queries")
    assert resp.status_code == 200
    labels = [q["label"] for q in resp.json()]
    assert "Alpha" in labels
    assert "Beta" in labels


def test_get_query_by_id(app_client: TestClient):
    """GET /analyst/queries/{id} returns the specific saved query."""
    save_resp = app_client.post(
        f"{BASE}/queries", json={"label": "Locate-me", "filters": []}
    )
    qid = save_resp.json()["query_id"]
    resp = app_client.get(f"{BASE}/queries/{qid}")
    assert resp.status_code == 200
    assert resp.json()["query_id"] == qid
    assert resp.json()["label"] == "Locate-me"


def test_get_query_missing_returns_404(app_client: TestClient):
    """GET /analyst/queries/{bad_id} returns 404."""
    resp = app_client.get(f"{BASE}/queries/does-not-exist")
    assert resp.status_code == 404


def test_delete_query_returns_204(app_client: TestClient):
    """DELETE /analyst/queries/{id} returns 204."""
    save_resp = app_client.post(f"{BASE}/queries", json={"filters": []})
    qid = save_resp.json()["query_id"]
    resp = app_client.delete(f"{BASE}/queries/{qid}")
    assert resp.status_code == 204
    # Confirm gone
    get_resp = app_client.get(f"{BASE}/queries/{qid}")
    assert get_resp.status_code == 404


def test_execute_saved_query(app_client: TestClient):
    """POST /analyst/queries/{id}/execute executes a saved query."""
    save_resp = app_client.post(f"{BASE}/queries", json={"filters": [], "limit": 5})
    qid = save_resp.json()["query_id"]
    exec_resp = app_client.post(f"{BASE}/queries/{qid}/execute")
    assert exec_resp.status_code == 200
    data = exec_resp.json()
    assert "total_matched" in data
    assert "returned_count" in data


def test_execute_missing_saved_query_returns_404(app_client: TestClient):
    """POST /analyst/queries/{bad_id}/execute returns 404."""
    resp = app_client.post(f"{BASE}/queries/no-such-id/execute")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Tests — Briefing surface
# ──────────────────────────────────────────────────────────────────────────────


def test_post_briefings_generates_briefing(app_client: TestClient):
    """POST /analyst/briefings generates a new briefing."""
    payload = {
        "title": "Integration Test Briefing",
        "sections": ["executive_summary", "timeline"],
        "classification_label": "UNCLASSIFIED",
    }
    resp = app_client.post(f"{BASE}/briefings", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Integration Test Briefing"
    assert "briefing_id" in data
    assert "content" in data
    assert "executive_summary" in data["content"]
    assert "citations" in data
    assert "confidence_assessment" in data


def test_get_briefings_returns_list(app_client: TestClient):
    """GET /analyst/briefings returns all generated briefings."""
    app_client.post(
        f"{BASE}/briefings",
        json={"title": "Briefing One", "sections": ["executive_summary"]},
    )
    app_client.post(
        f"{BASE}/briefings",
        json={"title": "Briefing Two", "sections": ["timeline"]},
    )
    resp = app_client.get(f"{BASE}/briefings")
    assert resp.status_code == 200
    titles = [b["title"] for b in resp.json()]
    assert "Briefing One" in titles
    assert "Briefing Two" in titles


def test_get_briefing_by_id(app_client: TestClient):
    """GET /analyst/briefings/{id} returns specific briefing."""
    create_resp = app_client.post(
        f"{BASE}/briefings",
        json={"title": "Find Me", "sections": ["executive_summary"]},
    )
    bid = create_resp.json()["briefing_id"]
    resp = app_client.get(f"{BASE}/briefings/{bid}")
    assert resp.status_code == 200
    assert resp.json()["briefing_id"] == bid


def test_get_briefing_missing_returns_404(app_client: TestClient):
    """GET /analyst/briefings/{bad_id} returns 404."""
    resp = app_client.get(f"{BASE}/briefings/no-such-briefing")
    assert resp.status_code == 404


def test_get_briefing_text_returns_plain_text(app_client: TestClient):
    """GET /analyst/briefings/{id}/text returns text/plain content."""
    create_resp = app_client.post(
        f"{BASE}/briefings",
        json={
            "title": "Text Export Test",
            "sections": ["executive_summary"],
            "classification_label": "RESTRICTED",
        },
    )
    bid = create_resp.json()["briefing_id"]
    resp = app_client.get(f"{BASE}/briefings/{bid}/text")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "RESTRICTED" in resp.text


def test_get_briefing_text_missing_returns_404(app_client: TestClient):
    """GET /analyst/briefings/{bad_id}/text returns 404."""
    resp = app_client.get(f"{BASE}/briefings/no-such/text")
    assert resp.status_code == 404


def test_briefing_from_investigation_generates(app_client: TestClient):
    """POST /analyst/briefings/from-investigation/{inv_id} generates from investigation."""
    # Create an investigation first
    inv_resp = app_client.post(
        "/api/v1/investigations",
        json={"name": "Ship Smuggling Case", "description": "Test investigation"},
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    resp = app_client.post(f"{BASE}/briefings/from-investigation/{inv_id}")
    assert resp.status_code == 201
    data = resp.json()
    assert data["investigation_id"] == inv_id
    assert "briefing_id" in data
    assert "content" in data


def test_briefing_from_investigation_missing_returns_404(app_client: TestClient):
    """POST /analyst/briefings/from-investigation/{bad_id} returns 404."""
    resp = app_client.post(f"{BASE}/briefings/from-investigation/no-such-investigation")
    assert resp.status_code == 404


def test_briefing_filter_by_investigation_id(app_client: TestClient):
    """GET /analyst/briefings?investigation_id= filters by investigation."""
    # Create investigation and briefing linked to it
    inv_resp = app_client.post(
        "/api/v1/investigations",
        json={"name": "Linked Investigation"},
    )
    inv_id = inv_resp.json()["id"]
    app_client.post(f"{BASE}/briefings/from-investigation/{inv_id}")

    # Also create an unlinked briefing
    app_client.post(f"{BASE}/briefings", json={"title": "Unlinked", "sections": ["timeline"]})

    resp = app_client.get(f"{BASE}/briefings", params={"investigation_id": inv_id})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert all(b["investigation_id"] == inv_id for b in items)


def test_post_query_with_event_type_filter_shape(app_client: TestClient):
    """POST /analyst/query with a text filter returns correct shape."""
    payload = {
        "filters": [
            {"field": "text", "operator": "contains", "value": "vessel"}
        ],
        "limit": 100,
    }
    resp = app_client.post(f"{BASE}/query", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["events"], list)
    assert isinstance(data["sources_cited"], list)
