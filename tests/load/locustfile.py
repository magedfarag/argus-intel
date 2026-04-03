"""Locust load test for the Construction Activity Monitor API — P5-1.7.

Performance targets (baseline, define in P5-1.7 milestone):
  - POST /api/v1/events/search:   p95 < 200 ms at 50 RPS
  - GET  /api/v1/health/sources:  p95 < 100 ms at 20 RPS
  - GET  /api/v1/events/timeline: p95 < 150 ms at 30 RPS

Usage:
    pip install locust
    locust -f tests/load/locustfile.py --host http://localhost:8000
    # or headless:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
           --headless -u 50 -r 10 --run-time 60s

Environment variables:
    LOCUST_API_KEY      API key for x-api-key header (optional)
    LOCUST_AOI_ID       AOI ID to use in search requests (optional)
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta, timezone

from locust import HttpUser, between, task


API_KEY = os.getenv("LOCUST_API_KEY", "")
AOI_ID  = os.getenv("LOCUST_AOI_ID", "test-aoi-1")

# Fixed 30-day window ending "now" so repeated runs use a stable window
_END   = "2026-03-28T00:00:00Z"
_START = "2026-02-26T00:00:00Z"


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


class AnalystUser(HttpUser):
    """Simulates an analyst interacting with the geoint platform."""

    wait_time = between(0.5, 2.0)

    # ── Read-heavy tasks (high weight) ────────────────────────────────────────

    @task(5)
    def event_search(self):
        """POST /api/v1/events/search — primary analyst workflow."""
        payload = {
            "start_time": _START,
            "end_time": _END,
            "limit": 50,
        }
        with self.client.post(
            "/api/v1/events/search",
            json=payload,
            headers=_headers(),
            catch_response=True,
            name="POST /api/v1/events/search",
        ) as resp:
            if resp.status_code not in (200, 422):
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(4)
    def timeline_aggregation(self):
        """GET /api/v1/events/timeline — timeline bar chart."""
        with self.client.get(
            f"/api/v1/events/timeline"
            f"?start_time={_START}&end_time={_END}&bucket_minutes=60",
            headers=_headers(),
            catch_response=True,
            name="GET /api/v1/events/timeline",
        ) as resp:
            if resp.status_code not in (200, 422):
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(3)
    def health_dashboard(self):
        """GET /api/v1/health/sources — source health panel."""
        with self.client.get(
            "/api/v1/health/sources",
            headers=_headers(),
            catch_response=True,
            name="GET /api/v1/health/sources",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(2)
    def list_aois(self):
        """GET /api/v1/aois — AOI list panel."""
        with self.client.get(
            "/api/v1/aois",
            headers=_headers(),
            catch_response=True,
            name="GET /api/v1/aois",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(2)
    def sources_list(self):
        """GET /api/v1/events/sources — source catalog panel."""
        with self.client.get(
            "/api/v1/events/sources",
            headers=_headers(),
            catch_response=True,
            name="GET /api/v1/events/sources",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def imagery_providers(self):
        """GET /api/v1/imagery/providers — provider catalog."""
        with self.client.get(
            "/api/v1/imagery/providers",
            headers=_headers(),
            catch_response=True,
            name="GET /api/v1/imagery/providers",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def health_check(self):
        """GET /healthz — liveness probe."""
        with self.client.get(
            "/healthz",
            catch_response=True,
            name="GET /healthz",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def playback_query(self):
        """POST /api/v1/playback/query — timeline playback controller."""
        payload = {
            "start_time": _START,
            "end_time": _END,
            "limit": 100,
        }
        with self.client.post(
            "/api/v1/playback/query",
            json=payload,
            headers=_headers(),
            catch_response=True,
            name="POST /api/v1/playback/query",
        ) as resp:
            if resp.status_code not in (200, 422):
                resp.failure(f"Unexpected status {resp.status_code}")
