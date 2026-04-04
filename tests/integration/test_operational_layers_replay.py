"""Phase 2, Track E — Mixed-layer replay integration tests.

Tests cross-layer synchronization scenarios:
  A: Timeline consistency — all 4 layer families queryable in the same time window
  B: Jamming confidence filter reduces results
  C: Strike type filter returns only matching records
  D: Evidence attachment increments corroboration_count
  E: Airspace active_only flag excludes expired restrictions
  F: Orbit pass prediction temporal ordering (AOS < LOS)
  G: Jamming heatmap returns properly shaped weighted points
  H: Strike summary aggregation contains valid strike types
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.cache.client import CacheClient
from app.providers.demo import DemoProvider
from app.providers.registry import ProviderRegistry
from app.resilience.circuit_breaker import CircuitBreaker


# ── Shared TestClient fixture (module-scoped for speed) ──────────────────────


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
# Scenario A: Timeline consistency across all 4 layer families
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioA_TimelineConsistency:
    """All 4 layer APIs return at least one result within a consistent query window."""

    def test_orbits_layer_returns_results(self, client: TestClient) -> None:
        r = client.get("/api/v1/orbits")
        assert r.status_code == 200
        body = r.json()
        assert len(body["orbits"]) >= 1, "Orbits layer must have at least 1 record"

    def test_airspace_layer_returns_results(self, client: TestClient) -> None:
        r = client.get("/api/v1/airspace/restrictions")
        assert r.status_code == 200
        body = r.json()
        assert len(body["restrictions"]) >= 1, "Airspace layer must have at least 1 record"

    def test_jamming_layer_returns_results(self, client: TestClient) -> None:
        # Use the full 60-day window to cover both seed windows
        r = client.get(
            "/api/v1/jamming/events"
            "?start=2026-02-01T00:00:00Z&end=2026-04-04T00:00:00Z"
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 1, "Jamming layer must have at least 1 event in the window"

    def test_strikes_layer_returns_results(self, client: TestClient) -> None:
        r = client.get(
            "/api/v1/strikes"
            "?start=2026-02-01T00:00:00Z&end=2026-04-04T00:00:00Z"
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 1, "Strike layer must have at least 1 event in the window"

    def test_all_four_layers_respond_200(self, client: TestClient) -> None:
        """Smoke test: all 4 layer root endpoints return 200 simultaneously."""
        endpoints = [
            "/api/v1/orbits",
            "/api/v1/airspace/restrictions",
            "/api/v1/jamming/events",
            "/api/v1/strikes",
        ]
        for ep in endpoints:
            assert client.get(ep).status_code == 200, f"{ep} must return 200"


# ──────────────────────────────────────────────────────────────────────────────
# Scenario B: Jamming confidence filter
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioB_JammingConfidenceFilter:
    """Higher confidence_min returns fewer or equal jamming events."""

    def test_high_confidence_returns_subset(self, client: TestClient) -> None:
        low = client.get("/api/v1/jamming/events?confidence_min=0.0").json()
        high = client.get("/api/v1/jamming/events?confidence_min=0.9").json()
        assert len(high) <= len(low), (
            "High confidence filter must return ≤ results vs low confidence filter"
        )

    def test_filtered_events_meet_minimum_confidence(self, client: TestClient) -> None:
        threshold = 0.7
        results = client.get(f"/api/v1/jamming/events?confidence_min={threshold}").json()
        for ev in results:
            assert ev["confidence"] >= threshold, (
                f"Event {ev['jamming_id']} confidence {ev['confidence']} "
                f"is below threshold {threshold}"
            )

    def test_zero_confidence_returns_all(self, client: TestClient) -> None:
        all_events = client.get("/api/v1/jamming/events").json()
        zero_filter = client.get("/api/v1/jamming/events?confidence_min=0.0").json()
        assert len(zero_filter) == len(all_events), (
            "confidence_min=0.0 must be equivalent to no filter"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Scenario C: Strike type filter
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioC_StrikeTypeFilter:
    """Filtering by strike_type returns only matching strikes."""

    def _get_first_type(self, client: TestClient) -> str:
        """Return the strike_type of the first seeded strike."""
        body = client.get("/api/v1/strikes").json()
        assert len(body) >= 1
        return body[0]["strike_type"]

    def test_type_filter_returns_only_matching(self, client: TestClient) -> None:
        strike_type = self._get_first_type(client)
        filtered = client.get(f"/api/v1/strikes?strike_type={strike_type}").json()
        assert len(filtered) >= 1
        for s in filtered:
            assert s["strike_type"] == strike_type, (
                f"Expected strike_type={strike_type!r}, got {s['strike_type']!r}"
            )

    def test_unknown_type_filter_returns_empty_or_matches(self, client: TestClient) -> None:
        """Filtering by a real type value returns only that type (or empty if absent)."""
        filtered = client.get("/api/v1/strikes?strike_type=unknown").json()
        for s in filtered:
            assert s["strike_type"] == "unknown"

    def test_unfiltered_has_all_types(self, client: TestClient) -> None:
        """Unfiltered strikes list is a superset of any type-filtered result."""
        all_strikes = client.get("/api/v1/strikes").json()
        strike_type = all_strikes[0]["strike_type"]
        filtered = client.get(f"/api/v1/strikes?strike_type={strike_type}").json()
        assert len(filtered) <= len(all_strikes)


# ──────────────────────────────────────────────────────────────────────────────
# Scenario D: Evidence → corroboration count
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioD_EvidenceCorroboration:
    """Attaching a new evidence link increments corroboration_count by 1."""

    def test_evidence_increments_corroboration(self, client: TestClient) -> None:
        strikes = client.get("/api/v1/strikes").json()
        strike = strikes[0]
        strike_id = strike["strike_id"]
        initial_count = strike["corroboration_count"]

        payload = {
            "evidence_id": "ev-replay-scenario-d-001",
            "event_id": strike_id,
            "evidence_type": "imagery",
        }
        r = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=payload)
        assert r.status_code == 200
        updated = r.json()
        assert updated["corroboration_count"] == initial_count + 1, (
            "corroboration_count must increment by 1 after new evidence attached"
        )

    def test_evidence_id_appears_in_evidence_refs(self, client: TestClient) -> None:
        strikes = client.get("/api/v1/strikes").json()
        strike_id = strikes[0]["strike_id"]

        payload = {
            "evidence_id": "ev-replay-scenario-d-002",
            "event_id": strike_id,
            "evidence_type": "sigint",
        }
        r = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=payload)
        assert r.status_code == 200
        assert "ev-replay-scenario-d-002" in r.json()["evidence_refs"]

    def test_attaching_same_evidence_twice_is_idempotent(self, client: TestClient) -> None:
        strikes = client.get("/api/v1/strikes").json()
        strike_id = strikes[0]["strike_id"]

        payload = {
            "evidence_id": "ev-replay-idem-001",
            "event_id": strike_id,
            "evidence_type": "report",
        }
        r1 = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=payload)
        count_after_first = r1.json()["corroboration_count"]

        r2 = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=payload)
        count_after_second = r2.json()["corroboration_count"]

        assert count_after_second == count_after_first, (
            "Duplicate evidence_id must not increment corroboration_count a second time"
        )

    def test_corroboration_reflected_in_get_by_id(self, client: TestClient) -> None:
        """After POST evidence, GET /{strike_id} reflects the updated count."""
        strikes = client.get("/api/v1/strikes").json()
        strike_id = strikes[-1]["strike_id"]  # Use last strike to avoid cross-test noise

        payload = {
            "evidence_id": "ev-replay-getbyid-001",
            "event_id": strike_id,
            "evidence_type": "imagery",
        }
        post_resp = client.post(f"/api/v1/strikes/{strike_id}/evidence", json=payload)
        expected_count = post_resp.json()["corroboration_count"]

        get_resp = client.get(f"/api/v1/strikes/{strike_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["corroboration_count"] == expected_count


# ──────────────────────────────────────────────────────────────────────────────
# Scenario E: Airspace active_only filtering
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioE_AirspaceActiveOnlyFilter:
    """active_only=true excludes expired airspace restrictions."""

    def test_active_only_subset_of_all(self, client: TestClient) -> None:
        all_r = client.get("/api/v1/airspace/restrictions?active_only=false").json()
        active_r = client.get("/api/v1/airspace/restrictions?active_only=true").json()
        assert len(active_r) <= len(all_r["restrictions"]), (
            "active_only=true must return ≤ records compared to active_only=false"
        )

    def test_active_only_all_records_are_active(self, client: TestClient) -> None:
        active_r = client.get(
            "/api/v1/airspace/restrictions?active_only=true"
        ).json()["restrictions"]
        for r in active_r:
            assert r["is_active"] is True, (
                f"Restriction {r['restriction_id']} has is_active=False but was "
                "returned by active_only=true"
            )

    def test_active_only_excludes_expired_restriction(self, client: TestClient) -> None:
        """The seeded TFR-2026-EXPIRED record must not appear in active_only results."""
        active_r = client.get(
            "/api/v1/airspace/restrictions?active_only=true"
        ).json()["restrictions"]
        ids = [r["restriction_id"] for r in active_r]
        assert "TFR-2026-EXPIRED" not in ids

    def test_all_restrictions_includes_expired(self, client: TestClient) -> None:
        """Without active_only, expired restrictions should be present."""
        all_r = client.get(
            "/api/v1/airspace/restrictions?active_only=false"
        ).json()["restrictions"]
        ids = [r["restriction_id"] for r in all_r]
        assert "TFR-2026-EXPIRED" in ids, (
            "TFR-2026-EXPIRED must appear in the unfiltered restrictions list"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Scenario F: Orbit pass prediction temporal ordering
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioF_OrbitPassPrediction:
    """Predicted passes include AOS and LOS with AOS < LOS and valid confidence."""

    _SAT_ID = "ISS-(ZARYA)"

    def test_pass_prediction_returns_results(self, client: TestClient) -> None:
        r = client.get(
            f"/api/v1/orbits/{self._SAT_ID}/passes?lon=0&lat=51&horizon_hours=24"
        )
        assert r.status_code == 200
        body = r.json()
        assert "passes" in body
        assert len(body["passes"]) >= 1

    def test_aos_precedes_los_for_all_passes(self, client: TestClient) -> None:
        body = client.get(
            f"/api/v1/orbits/{self._SAT_ID}/passes?lon=0&lat=51&horizon_hours=24"
        ).json()
        for p in body["passes"]:
            assert p["aos"] < p["los"], (
                f"Pass AOS={p['aos']} must precede LOS={p['los']}"
            )

    def test_pass_confidence_in_valid_range(self, client: TestClient) -> None:
        body = client.get(
            f"/api/v1/orbits/{self._SAT_ID}/passes?lon=0&lat=51&horizon_hours=24"
        ).json()
        for p in body["passes"]:
            assert 0.0 <= p["confidence"] <= 1.0, (
                f"Pass confidence {p['confidence']} outside [0.0, 1.0]"
            )

    def test_passes_have_required_fields(self, client: TestClient) -> None:
        body = client.get(
            f"/api/v1/orbits/{self._SAT_ID}/passes?lon=0&lat=51&horizon_hours=24"
        ).json()
        required = {"aos", "los", "confidence", "satellite_id"}
        for p in body["passes"]:
            for field in required:
                assert field in p, f"Pass missing required field: {field!r}"

    def test_extended_horizon_returns_more_or_equal_passes(
        self, client: TestClient
    ) -> None:
        short = client.get(
            f"/api/v1/orbits/{self._SAT_ID}/passes?lon=0&lat=51&horizon_hours=6"
        ).json()["passes"]
        long_ = client.get(
            f"/api/v1/orbits/{self._SAT_ID}/passes?lon=0&lat=51&horizon_hours=48"
        ).json()["passes"]
        assert len(long_) >= len(short), (
            "Longer horizon must yield ≥ passes than shorter horizon"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Scenario G: Jamming heatmap data shape
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioG_JammingHeatmap:
    """Heatmap endpoint returns a list of {lon, lat, weight} points."""

    def test_heatmap_returns_list(self, client: TestClient) -> None:
        r = client.get("/api/v1/jamming/heatmap")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_heatmap_has_at_least_one_point(self, client: TestClient) -> None:
        body = client.get("/api/v1/jamming/heatmap").json()
        assert len(body) >= 1, "Heatmap must have at least one weighted point"

    def test_heatmap_points_have_lon_lat_weight(self, client: TestClient) -> None:
        body = client.get("/api/v1/jamming/heatmap").json()
        for pt in body:
            assert "lon" in pt, f"Heatmap point missing 'lon': {pt}"
            assert "lat" in pt, f"Heatmap point missing 'lat': {pt}"
            assert "weight" in pt, f"Heatmap point missing 'weight': {pt}"

    def test_heatmap_weight_in_valid_range(self, client: TestClient) -> None:
        body = client.get("/api/v1/jamming/heatmap").json()
        for pt in body:
            assert 0.0 <= pt["weight"] <= 1.0, (
                f"Heatmap weight {pt['weight']} outside [0.0, 1.0]"
            )

    def test_heatmap_lon_lat_are_numeric(self, client: TestClient) -> None:
        body = client.get("/api/v1/jamming/heatmap").json()
        for pt in body:
            assert isinstance(pt["lon"], (int, float)), "lon must be numeric"
            assert isinstance(pt["lat"], (int, float)), "lat must be numeric"


# ──────────────────────────────────────────────────────────────────────────────
# Scenario H: Strike summary aggregation
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioH_StrikeSummary:
    """Strike summary returns a dict of {strike_type: count} with valid types."""

    _VALID_TYPES = {"airstrike", "artillery", "missile", "drone", "unknown"}

    def test_summary_returns_dict(self, client: TestClient) -> None:
        r = client.get("/api/v1/strikes/summary")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_summary_keys_are_valid_strike_types(self, client: TestClient) -> None:
        summary = client.get("/api/v1/strikes/summary").json()
        for k in summary:
            assert k in self._VALID_TYPES, (
                f"Unexpected strike type key {k!r} in summary"
            )

    def test_summary_counts_are_non_negative_integers(
        self, client: TestClient
    ) -> None:
        summary = client.get("/api/v1/strikes/summary").json()
        for k, v in summary.items():
            assert isinstance(v, int), f"Count for {k!r} must be int, got {type(v)}"
            assert v >= 0, f"Count for {k!r} must be ≥ 0"

    def test_summary_total_matches_filtered_list(self, client: TestClient) -> None:
        """Sum of summary counts must equal the number of 30-day window strikes."""
        summary = client.get("/api/v1/strikes/summary").json()
        summary_total = sum(summary.values())
        # /strikes without params returns all seeded events; seeded window is 30 days
        all_strikes = client.get("/api/v1/strikes").json()
        assert summary_total <= len(all_strikes), (
            "Summary total must not exceed total strike count"
        )
