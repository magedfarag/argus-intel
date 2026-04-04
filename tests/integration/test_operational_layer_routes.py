"""Integration tests for Phase 2 operational-layer HTTP endpoints.

Uses FastAPI TestClient against the full ARGUS app (app.main).
Tests every new route added in Phase 2:
  - /api/v1/orbits
  - /api/v1/airspace
  - /api/v1/jamming
  - /api/v1/strikes
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.cache.client import CacheClient
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker


# ── Shared TestClient fixture (session-scoped for speed) ─────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    reg = ProviderRegistry()
    reg.register(DemoProvider())
    dependencies.set_registry(reg)
    dependencies.set_cache(CacheClient())
    dependencies.set_breaker(CircuitBreaker())
    from app.main import app
    from app.resilience.rate_limiter import limiter
    limiter.reset()
    return TestClient(app, raise_server_exceptions=True)


# ──────────────────────────────────────────────────────────────────────────────
# Orbits — /api/v1/orbits
# ──────────────────────────────────────────────────────────────────────────────


class TestOrbitsEndpoints:
    def test_list_orbits_200(self, client):
        r = client.get("/api/v1/orbits")
        assert r.status_code == 200

    def test_list_orbits_returns_list_with_items(self, client):
        r = client.get("/api/v1/orbits")
        body = r.json()
        assert "orbits" in body
        assert isinstance(body["orbits"], list)
        assert len(body["orbits"]) >= 1

    def test_list_orbits_total_matches_length(self, client):
        r = client.get("/api/v1/orbits")
        body = r.json()
        assert body["total"] == len(body["orbits"])

    def test_get_orbit_known_satellite_200(self, client):
        # ISS should always be seeded
        r = client.get("/api/v1/orbits/ISS-(ZARYA)")
        assert r.status_code == 200

    def test_get_orbit_returns_satellite_id_field(self, client):
        r = client.get("/api/v1/orbits/ISS-(ZARYA)")
        body = r.json()
        assert "satellite_id" in body
        assert body["satellite_id"] == "ISS-(ZARYA)"

    def test_get_orbit_unknown_satellite_404(self, client):
        r = client.get("/api/v1/orbits/UNKNOWN-SAT-XXXXXX")
        assert r.status_code == 404

    def test_get_passes_200(self, client):
        r = client.get("/api/v1/orbits/ISS-(ZARYA)/passes?lon=0&lat=51&horizon_hours=24")
        assert r.status_code == 200

    def test_get_passes_returns_list(self, client):
        r = client.get("/api/v1/orbits/ISS-(ZARYA)/passes?lon=0&lat=51&horizon_hours=24")
        body = r.json()
        assert "passes" in body
        assert isinstance(body["passes"], list)
        assert len(body["passes"]) >= 1

    def test_get_passes_each_has_aos_and_los(self, client):
        r = client.get("/api/v1/orbits/ISS-(ZARYA)/passes?lon=0&lat=51&horizon_hours=24")
        for p in r.json()["passes"]:
            assert "aos" in p
            assert "los" in p

    def test_get_passes_unknown_satellite_404(self, client):
        r = client.get("/api/v1/orbits/UNKNOWN-SAT-XXXXXX/passes?lon=0&lat=51&horizon_hours=24")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Airspace — /api/v1/airspace
# ──────────────────────────────────────────────────────────────────────────────


class TestAirspaceEndpoints:
    def test_list_restrictions_200(self, client):
        r = client.get("/api/v1/airspace/restrictions")
        assert r.status_code == 200

    def test_list_restrictions_returns_list(self, client):
        r = client.get("/api/v1/airspace/restrictions")
        body = r.json()
        assert "restrictions" in body
        assert isinstance(body["restrictions"], list)
        assert len(body["restrictions"]) >= 1

    def test_list_restrictions_active_only_filter(self, client):
        all_r = client.get("/api/v1/airspace/restrictions").json()["restrictions"]
        active_r = client.get("/api/v1/airspace/restrictions?active_only=true").json()["restrictions"]
        # active_only results must all be active
        assert all(r["is_active"] for r in active_r)
        # active_only should have fewer or equal records than unfiltered
        assert len(active_r) <= len(all_r)

    def test_list_restrictions_active_only_excludes_expired(self, client):
        active_r = client.get("/api/v1/airspace/restrictions?active_only=true").json()["restrictions"]
        ids = [r["restriction_id"] for r in active_r]
        assert "TFR-2026-EXPIRED" not in ids

    def test_get_restriction_by_id_200(self, client):
        r = client.get("/api/v1/airspace/restrictions/TFR-2026-0001")
        assert r.status_code == 200

    def test_get_restriction_by_id_unknown_404(self, client):
        r = client.get("/api/v1/airspace/restrictions/DOES-NOT-EXIST")
        assert r.status_code == 404

    def test_list_notams_200(self, client):
        r = client.get("/api/v1/airspace/notams")
        assert r.status_code == 200

    def test_list_notams_returns_list(self, client):
        r = client.get("/api/v1/airspace/notams")
        body = r.json()
        assert "notams" in body
        assert isinstance(body["notams"], list)
        assert len(body["notams"]) >= 1

    def test_list_notams_icao_filter(self, client):
        r = client.get("/api/v1/airspace/notams?icao=KDCA")
        body = r.json()
        assert r.status_code == 200
        for n in body["notams"]:
            assert n["location_icao"] == "KDCA"

    def test_get_notam_by_id_200(self, client):
        r = client.get("/api/v1/airspace/notams/notam-001")
        assert r.status_code == 200

    def test_get_notam_by_id_unknown_404(self, client):
        r = client.get("/api/v1/airspace/notams/notam-does-not-exist")
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Jamming — /api/v1/jamming
# ──────────────────────────────────────────────────────────────────────────────


class TestJammingEndpoints:
    def test_list_jamming_events_200(self, client):
        r = client.get("/api/v1/jamming/events")
        assert r.status_code == 200

    def test_list_jamming_events_returns_list(self, client):
        r = client.get("/api/v1/jamming/events")
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_list_jamming_events_have_required_fields(self, client):
        body = client.get("/api/v1/jamming/events").json()
        for ev in body:
            assert "jamming_id" in ev
            assert "detected_at" in ev
            assert "confidence" in ev

    def test_get_jamming_event_by_id_200(self, client):
        events = client.get("/api/v1/jamming/events").json()
        first_id = events[0]["jamming_id"]
        r = client.get(f"/api/v1/jamming/events/{first_id}")
        assert r.status_code == 200

    def test_get_jamming_event_unknown_404(self, client):
        r = client.get("/api/v1/jamming/events/does-not-exist-xyz")
        assert r.status_code == 404

    def test_get_heatmap_200(self, client):
        r = client.get("/api/v1/jamming/heatmap")
        assert r.status_code == 200

    def test_heatmap_returns_list_of_points(self, client):
        body = client.get("/api/v1/jamming/heatmap").json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_heatmap_each_point_has_lon_lat_weight(self, client):
        body = client.get("/api/v1/jamming/heatmap").json()
        for pt in body:
            assert "lon" in pt
            assert "lat" in pt
            assert "weight" in pt

    def test_heatmap_weight_positive(self, client):
        body = client.get("/api/v1/jamming/heatmap").json()
        for pt in body:
            assert pt["weight"] >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Strikes — /api/v1/strikes
# ──────────────────────────────────────────────────────────────────────────────


class TestStrikeEndpoints:
    def test_list_strikes_200(self, client):
        r = client.get("/api/v1/strikes")
        assert r.status_code == 200

    def test_list_strikes_returns_list(self, client):
        body = client.get("/api/v1/strikes").json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_list_strikes_have_required_fields(self, client):
        body = client.get("/api/v1/strikes").json()
        for ev in body:
            assert "strike_id" in ev
            assert "occurred_at" in ev
            assert "confidence" in ev
            assert "corroboration_count" in ev

    def test_get_summary_200(self, client):
        r = client.get("/api/v1/strikes/summary")
        assert r.status_code == 200

    def test_get_summary_returns_dict_with_strike_type_keys(self, client):
        body = client.get("/api/v1/strikes/summary").json()
        assert isinstance(body, dict)
        # Must have at least one strike_type key
        assert len(body) >= 1
        for v in body.values():
            assert isinstance(v, int)
            assert v >= 1

    def test_get_strike_by_id_200(self, client):
        events = client.get("/api/v1/strikes").json()
        first_id = events[0]["strike_id"]
        r = client.get(f"/api/v1/strikes/{first_id}")
        assert r.status_code == 200

    def test_get_strike_unknown_404(self, client):
        r = client.get("/api/v1/strikes/does-not-exist-xyz")
        assert r.status_code == 404

    def test_attach_evidence_increments_corroboration(self, client):
        events = client.get("/api/v1/strikes").json()
        strike_id = events[0]["strike_id"]
        before_count = events[0]["corroboration_count"]

        link_payload = {
            "evidence_id": "ev-integration-test-001",
            "event_id": strike_id,
            "evidence_type": "imagery",
        }
        r = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=link_payload)
        assert r.status_code == 200
        updated = r.json()
        assert updated["corroboration_count"] == before_count + 1

    def test_attach_evidence_adds_evidence_id_to_refs(self, client):
        events = client.get("/api/v1/strikes").json()
        strike_id = events[0]["strike_id"]

        link_payload = {
            "evidence_id": "ev-integration-test-002",
            "event_id": strike_id,
            "evidence_type": "report",
        }
        r = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=link_payload)
        assert r.status_code == 200
        assert "ev-integration-test-002" in r.json()["evidence_refs"]

    def test_attach_evidence_idempotent_same_id(self, client):
        events = client.get("/api/v1/strikes").json()
        strike_id = events[0]["strike_id"]

        link_payload = {
            "evidence_id": "ev-idem-test-001",
            "event_id": strike_id,
            "evidence_type": "imagery",
        }
        r1 = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=link_payload)
        count_after_first = r1.json()["corroboration_count"]

        r2 = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=link_payload)
        count_after_second = r2.json()["corroboration_count"]

        assert count_after_second == count_after_first

    def test_attach_evidence_to_unknown_strike_404(self, client):
        link_payload = {
            "evidence_id": "ev-404-test",
            "event_id": "nonexistent-strike",
            "evidence_type": "imagery",
        }
        r = client.post("/api/v1/strikes/nonexistent-strike/evidence", json=link_payload)
        assert r.status_code == 404
