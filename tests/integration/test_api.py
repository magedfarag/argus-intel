"""Integration tests for all API endpoints."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from app import dependencies
from app.cache.client import CacheClient
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker

POLYGON = {"type": "Polygon", "coordinates": [[[30.0,50.0],[30.1,50.0],[30.1,50.1],[30.0,50.1],[30.0,50.0]]]}

@pytest.fixture(scope="module")
def client():
    reg = ProviderRegistry(); reg.register(DemoProvider())
    dependencies.set_registry(reg)
    dependencies.set_cache(CacheClient())
    dependencies.set_breaker(CircuitBreaker())
    from app.main import app
    from app.resilience.rate_limiter import limiter
    limiter.reset()
    return TestClient(app, raise_server_exceptions=True)

def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"

def test_config_returns_today(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["today"] == "2026-03-28"

def test_providers_includes_demo(client):
    r = client.get("/api/providers")
    assert r.status_code == 200
    assert any(p["name"] == "demo" for p in r.json()["providers"])

def test_analyze_demo_3_changes(client):
    r = client.post("/api/analyze", json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28", "provider": "demo"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_demo"] is True and body["stats"]["total_changes"] == 3

def test_analyze_change_has_required_fields(client):
    r = client.post("/api/analyze", json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28", "provider": "demo"})
    c = r.json()["changes"][0]
    for f in ["change_id", "change_type", "confidence", "center", "bbox", "summary", "rationale"]:
        assert f in c

def test_analyze_invalid_geometry_422(client):
    r = client.post("/api/analyze", json={"geometry": {"type": "Point", "coordinates": [30.0, 50.0]}, "start_date": "2026-03-01", "end_date": "2026-03-28"})
    assert r.status_code == 422

def test_analyze_bad_date_order_422(client):
    r = client.post("/api/analyze", json={"geometry": POLYGON, "start_date": "2026-03-28", "end_date": "2026-03-01"})
    assert r.status_code == 422

def test_search_endpoint(client):
    r = client.post("/api/search", json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28", "provider": "demo"})
    assert r.status_code == 200 and "scenes" in r.json()

def test_credits_endpoint(client):
    assert client.get("/api/credits").status_code == 200

def test_jobs_without_redis_503(client):
    assert client.get("/api/jobs/test-id").status_code == 503

def test_root_serves_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "ARGUS API"


# ── V2 Export API (P1-5) ──────────────────────────────────────────────────────

_SEARCH_BODY = {
    "start_time": "2026-01-01T00:00:00Z",
    "end_time": "2026-12-31T23:59:59Z",
}


def test_export_empty_result_csv_completes(client):
    """Export with no matching events should return a completed job with header."""
    body = {"search": _SEARCH_BODY, "format": "csv"}
    r = client.post("/api/v1/exports", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "completed"
    assert data["format"] == "csv"
    assert "download_url" in data


def test_export_empty_result_geojson_completes(client):
    body = {"search": _SEARCH_BODY, "format": "geojson"}
    r = client.post("/api/v1/exports", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "completed"
    assert data["format"] == "geojson"


def test_export_download_csv(client):
    """End-to-end: create export then download the file."""
    body = {"search": _SEARCH_BODY, "format": "csv"}
    create_r = client.post("/api/v1/exports", json=body)
    assert create_r.status_code == 201
    job_id = create_r.json()["job_id"]

    dl_r = client.get(f"/api/v1/exports/{job_id}")
    assert dl_r.status_code == 200
    assert "text/csv" in dl_r.headers["content-type"]
    assert dl_r.headers.get("content-disposition", "").startswith("attachment")


def test_export_download_geojson(client):
    body = {"search": _SEARCH_BODY, "format": "geojson"}
    create_r = client.post("/api/v1/exports", json=body)
    assert create_r.status_code == 201
    job_id = create_r.json()["job_id"]

    dl_r = client.get(f"/api/v1/exports/{job_id}")
    assert dl_r.status_code == 200
    assert "geo+json" in dl_r.headers["content-type"]
    data = dl_r.json()
    assert data["type"] == "FeatureCollection"


def test_export_download_missing_job_404(client):
    r = client.get("/api/v1/exports/nonexistent-job-xyz")
    assert r.status_code == 404


def test_export_invalid_time_range_422(client):
    body = {"search": {"start_time": "2026-12-31T00:00:00Z", "end_time": "2026-01-01T00:00:00Z"}, "format": "csv"}
    r = client.post("/api/v1/exports", json=body)
    assert r.status_code == 422
