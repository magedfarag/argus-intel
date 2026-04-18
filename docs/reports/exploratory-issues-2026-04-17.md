# Exploratory Test Run — Issues Report
**Date:** 2026-04-17  
**Spec:** `e2e/full-features-exploratory.spec.ts`  
**Run command:** `pnpm run test:e2e -- e2e/full-features-exploratory.spec.ts --workers=1 --reporter=list`  
**Backend:** FastAPI on http://127.0.0.1:8000 (mode=staging)

---

## Test Results Summary

| # | Test | Result | Duration |
|---|------|--------|----------|
| 1 | shell, timeline, zones, and sensors | ✅ PASS (with warnings) | 7.0m |
| 2 | signals, replay, and intel analytics | ❌ FAIL (timeout, 2 attempts) | 10.1m |
| 3 | routes, dark ships, briefing, and cases | ⏭ SKIPPED (serial mode) | — |
| 4 | export, diff, cameras, and system health | ⏭ SKIPPED (serial mode) | — |

---

## JS / Frontend Issues

### ISSUE-FE-01 — Test 2 Timeout: Intel Analytics (Change Detection)
- **Severity:** High  
- **Location:** `e2e/full-features-exploratory.spec.ts:258` — test "signals, replay, and intel analytics"  
- **Error:**
  ```
  Test timeout of 600000ms exceeded.
  Error: apiRequestContext._wrapApiCall: ENOENT: no such file or directory, open
    '...\.playwright-artifacts-0\traces\bf908b0023eb72e4c801-...-recording1.trace'
  ```
- **Details:** The test completed signals search (step 05) and replay transport (step 06) but timed out at intel analytics (step 07). The change detection POST to `/api/v1/analytics/change-detection` either never responded or exceeded the 20s `waitForResponse` timeout, causing the overall 10-minute test timeout. A secondary error shows a missing trace file — the `.playwright-artifacts-0` directory was cleaned between the first and retry attempt, leaving a dangling trace path reference.
- **Reproduced:** Yes — failed on both attempt 1 and retry 1.
- **Evidence:** `test-results/full-features-exploratory--aab70--replay-and-intel-analytics-chromium/error-context.md`

### ISSUE-FE-02 — Test 1 Warnings: App Shell and Zones
- **Severity:** Low  
- **Location:** `e2e/full-features-exploratory.spec.ts:174` — steps "app shell and view modes" and "zones and AOI tools"  
- **Details:** Steps 01-shell and 03-zones captured warning screenshots (`01-shell-warning.png`, `03-zones-warning.png`). The test still passed (warnings are soft assertions captured via `createRecorder`). These indicate non-fatal UI issues during render mode cycling or AOI tool state transitions.
- **Evidence:** `test-results/full-features-exploratory--7791b--timeline-zones-and-sensors-chromium/01-shell-warning.png`, `03-zones-warning.png`

### ISSUE-FE-03 — Tests 3 & 4 Not Executed
- **Severity:** High (coverage gap)  
- **Location:** Tests "routes, dark ships, briefing, and cases" and "export, diff, cameras, and system health"  
- **Details:** Due to `test.describe.configure({ mode: 'serial' })`, Playwright skipped tests 3 and 4 after test 2 failed. The following features have **zero coverage** from this run:
  - Chokepoints / Routes panel
  - Dark Ships detection + Vessel Profile Modal
  - Intel Briefing panel
  - Investigations / Cases panel (create flow)
  - Export panel (CSV export)
  - Imagery Compare / Diff panel
  - Camera Feeds panel
  - Health Dashboard / System Status
- **Fix options:** Either (a) fix test 2 timeout so serial execution proceeds, or (b) run tests 3–4 independently with `--grep`.

---

## Backend Issues

### ISSUE-BE-01 — Redis Unavailable (No Connection)
- **Severity:** Medium  
- **Component:** `app/cache/client.py`, `app/resilience/circuit_breaker.py`  
- **Log:**
  ```
  WARNING app.cache.client: Redis unavailable (Error 10061 connecting to localhost:6379.
    No connection could be made because the target machine actively refused it.); using in-memory cache
  WARNING app.resilience.circuit_breaker: CircuitBreaker Redis unavailable; using in-process state
  ```
- **Impact:** Cache falls back to in-memory TTLCache (max=256, ttl=3600s). Circuit breaker state is in-process only — not shared across workers.

### ISSUE-BE-02 — PostgreSQL Unavailable (No Connection)
- **Severity:** Medium  
- **Component:** `app/services/job_manager.py`, `src/storage/database.py`  
- **Log:**
  ```
  WARNING app.services.job_manager: JobManager PostgreSQL unavailable
    (psycopg2.OperationalError: connection to server at localhost:5432 failed:
    Connection refused); using fallback
  ```
- **Impact:** JobManager falls back to in-memory. No persistent job history across restarts.

### ISSUE-BE-03 — GDELT Connector Disabled (HTTP 429 Rate Limited)
- **Severity:** Medium  
- **Component:** `src/connectors/registry.py` → `gdelt-doc`  
- **Log:**
  ```
  WARNING src.connectors.registry: Connector gdelt-doc unavailable at startup;
    registered but disabled: GDELT API unreachable: Client error '429 Too Many Requests'
    for url 'https://api.gdeltproject.org/api/v2/doc/doc?...'
  ```
- **Impact:** GDELT event data unavailable. Frontend GDELT layer will show no data.

### ISSUE-BE-04 — ACLED Connector Disabled (HTTP 403 Forbidden)
- **Severity:** Medium  
- **Component:** `src/connectors/registry.py` → `acled`, `src/services/operational_layer_service.py`  
- **Log:**
  ```
  WARNING src.connectors.registry: Connector acled unavailable at startup; registered but disabled:
    ACLED API unreachable: Client error '403 Forbidden'
  WARNING src.services.operational_layer_service: StrikeLayerService: live connector failed
    (AcledStrikeConnector: API unreachable: 403 Forbidden); using stub
  ```
- **Impact:** Conflict/strike data unavailable. Strikes layer uses stub data.

### ISSUE-BE-05 — NASA FIRMS Connector Disabled (HTTP 401 Unauthorized — DEMO_KEY)
- **Severity:** Medium  
- **Component:** `src/connectors/registry.py` → `nasa-firms`  
- **Log:**
  ```
  WARNING src.connectors.registry: Connector nasa-firms unavailable at startup; registered but disabled:
    NASA FIRMS unreachable: Client error '401 Unauthorized'
    for url 'https://firms.modaps.eosdis.nasa.gov/api/area/json/DEMO_KEY/...'
  ```
- **Impact:** Fire/thermal anomaly data unavailable. `DEMO_KEY` is expired or invalid — needs a real MAP_KEY.

### ISSUE-BE-06 — OpenAQ Connector Disabled (HTTP 401 Unauthorized)
- **Severity:** Low  
- **Component:** `src/connectors/registry.py` → `openaq`  
- **Log:**
  ```
  WARNING src.connectors.registry: Connector openaq unavailable at startup; registered but disabled:
    OpenAQ API unreachable: Client error '401 Unauthorized'
  ```
- **Impact:** Air quality data unavailable. API key missing or invalid.

### ISSUE-BE-07 — CelestrakConnector HTTP 404 (Orbit Layer Using Stub)
- **Severity:** Low  
- **Component:** `src/services/operational_layer_service.py`  
- **Log:**
  ```
  WARNING src.services.operational_layer_service: OrbitLayerService: live connector failed to connect
    (CelestrakConnector: endpoint returned HTTP 404); using stub
  ```
- **Impact:** Satellite orbit tracks use stub data. Celestrak API endpoint path may have changed.

### ISSUE-BE-08 — AIS Stream: Zero Messages / Live Poll Timeouts
- **Severity:** Medium  
- **Component:** `src/connectors/ais_stream.py`, `src/api/dark_ships.py`  
- **Log:**
  ```
  INFO  src.connectors.ais_stream: AisStreamConnector.fetch: collected 0 messages
  WARNING src.api.dark_ships: _live_poll_ais: timed out after 12s
  ```
- **Impact:** Real-time AIS ship positions unavailable. Dark ships detection depends on live AIS data. API key is present but WebSocket is returning no messages.

### ISSUE-BE-09 — Health Probe Failures at Startup
- **Severity:** Low  
- **Component:** `health_prober`  
- **Log:**
  ```
  WARNING health_prober: probe cdse-sentinel2: 
  WARNING health_prober: probe planetary-computer: 
  WARNING health_prober: probe ais-stream: 
  WARNING health_prober: probe nga-msi: 
  ```
- **Impact:** 4 of 15 connectors failing health probes. cdse-sentinel2, planetary-computer, nga-msi, ais-stream are degraded.

---

## Recommendations

1. **Fix test 2 timeout (ISSUE-FE-01):** The `waitForResults(20_000)` call in intel analytics step needs a longer timeout or the `/api/v1/analytics/change-detection` endpoint is slow/unresponsive in staging mode. Increase the per-step timeout or mock the response in staging.
2. **Start Docker infrastructure** before tests: `docker compose -f docker-compose.infra.yml up -d` to bring up Redis + PostgreSQL, resolving ISSUE-BE-01 and ISSUE-BE-02.
3. **Rotate API keys:** NASA FIRMS DEMO_KEY and OpenAQ key need replacement (ISSUE-BE-05, ISSUE-BE-06).
4. **Check Celestrak endpoint URL** — HTTP 404 suggests the endpoint path changed (ISSUE-BE-07).
5. **Investigate AIS Stream WebSocket** — key is present but no messages received (ISSUE-BE-08).
