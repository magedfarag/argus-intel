# Deployment Candidate Notes — ARGUS v6.0.0

**Release candidate date:** 2026-04-04  
**Branch:** `feature/P1-4-app-mode`  
**Status:** Ready for final sign-off and merge to `main`  
**Docker image tag convention:** `argus-intel:<git-sha>` (e.g. `argus-intel:abc1234`)

> This document captures the state of the platform at the production release candidate boundary.
> It must be reviewed by the release engineer and operations lead before merging to `main`.

---

## Phases Completed

| Phase | Title | Key Deliverables |
|---|---|---|
| 0 | Stabilize Current Branch | Frontend typecheck clean; CI gated; backend/frontend contracts aligned |
| 1 | Unified Historical Data Plane | AOI CRUD; CanonicalEvent store; STAC connectors; GDELT / AIS / OpenSky; Playback; Exports; Parquet |
| 2 | Article-Parity Operational Layers | Orbits, Airspace, Jamming, Strike routers; frontend OperationalLayersPanel; useTimelineSync |
| 3 | 3D World Upgrade | MapLibre GL JS + deck.gl; DEM terrain; Tile3DLayer; useScenePerformance; ADR-003 locked |
| 4 | Sensor Fusion and Simulator Modes | RenderMode (thermal / night / low-light); CameraFeedPanel; Detection overlays; multi-view time sync |
| 5 | Investigation Workflows | InvestigationService; AbsenceAnalyticsService; EvidencePackService; AnalystQueryService; InvestigationsPanel |
| 6 | Hardening and Release | RBAC / HMAC auth; AuditLoggingMiddleware; DATA_RETENTION_POLICY; app/metrics.py; connector health; alerting; runbooks; DR docs; release docs |

---

## Test Suite Summary (2026-04-04)

| Scope | Count |
|---|---|
| Backend tests passed | **1428** |
| Backend tests skipped (pre-existing: Celery/Redis CI, sentinel2/thumbnails) | 11 |
| Backend tests failed | **0** |
| Frontend TypeScript typecheck errors | **0** |

---

## Known Limitations Before Production Use

The following limitations are known and accepted for the release candidate. They must be
resolved before the platform handles sensitive or operational real-world data.

| # | Limitation | Impact | Recommended Resolution |
|---|---|---|---|
| L1 | All V2 stores are in-memory (`EventStore`, `InvestigationService`, `AbsenceAnalyticsService`, etc.) — data is lost on restart | **Critical** — no persistence | Migrate to PostGIS using Alembic migrations in `alembic/versions/` |
| L2 | Auth uses HMAC self-signed tokens — no external identity provider | **High** — no SSO, MFA, or token revocation | Integrate OAuth2 / OIDC provider (e.g. Keycloak, Auth0) |
| L3 | All connectors are stubs — no live external API calls activated by default | **High** — demo data only | Provide `AISSTREAM_API_KEY`, `OPENSKY_USERNAME/PASSWORD`, Sentinel-2/Landsat credentials |
| L4 | Rate limiting is per-worker in-process — not coordinated across multiple API workers | **Medium** — multi-worker deployments can exceed rate limits | Move rate limit state to Redis using `slowapi` Redis storage backend |
| L5 | 3D scene orbit paths use flat-earth TLE approximations — not WGS-84 accurate | **Low** — visual fidelity only | Replace `src/api/orbits.py` flat-earth math with a proper orbital mechanics library |
| L6 | Audit `user_id` stored as 16-char SHA-256 prefix — no central identity mapping | **Low** — investigations only | Deploy identity service and map SHA-256 prefixes to real user accounts |

---

## Required Environment Variables for Production

These variables **must** be set before exposing the platform to real users.

| Variable | Description | Example |
|---|---|---|
| `APP_MODE` | Operating mode | `production` |
| `API_KEY` | Master API key (any role resolves to analyst unless tiered keys also set) | long-entropy-string |
| `JWT_SECRET` | HMAC signing secret (minimum 32 chars) | another-long-entropy-string |
| `ADMIN_API_KEY` | Admin-tier API key | distinct-admin-key |
| `OPERATOR_API_KEY` | Operator-tier API key | distinct-operator-key |
| `ANALYST_API_KEY` | Analyst-tier API key | distinct-analyst-key |
| `ALLOWED_ORIGINS` | CORS allowed origins (comma-separated) | `https://argus.example.com` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `LOG_LEVEL` | Log verbosity | `INFO` |
| `LOG_FORMAT` | Log format | `json` |

Optional but recommended for full functionality:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (persistent job history and future V2 store migration) |
| `SENTINEL2_CLIENT_ID` / `SENTINEL2_CLIENT_SECRET` | Live Copernicus CDSE imagery |
| `AISSTREAM_API_KEY` | Live AIS maritime tracking |
| `OPENSKY_USERNAME` / `OPENSKY_PASSWORD` | Live aviation tracking |

See `.env.example` for complete annotated variable reference.

---

## Recommended Next Steps

1. **Postgres persistence** (`priority: critical`)  
   Run `alembic upgrade head` and wire `EventStore`, `InvestigationService`, and `AbsenceAnalyticsService` to PostGIS. Schema migrations are staged in `alembic/versions/`.

2. **Redis for shared state** (`priority: high`)  
   Move rate limiter and circuit breaker state to Redis to support multi-worker deployments.

3. **External identity provider** (`priority: high`)  
   Replace HMAC self-signed tokens with OAuth2 / OIDC. Retain `UserRole` enum and `require_*` dependency callables — only swap `create_access_token` and `_decode_role_token`.

4. **Live connector activation** (`priority: high`)  
   Provide API credentials for AIS, OpenSky, Sentinel-2, and Landsat. Validate live data flow with the connector health dashboard at `GET /api/v1/health/sources`.

5. **CI coverage gate** (`priority: medium`)  
   Add `pytest --cov=app --cov-fail-under=85 --cov=src --cov-fail-under=85` to `.github/workflows/ci.yml`.

6. **Load testing** (`priority: medium`)  
   Run `locust -f tests/load/locustfile.py --host http://localhost:8000` with 100 concurrent users to validate performance budgets before production traffic.

7. **WGS-84 orbit paths** (`priority: low`)  
   Replace flat-earth TLE approximations in `src/api/orbits.py` with a proper orbital mechanics library (e.g. `sgp4`).

---

## Merge and Deploy Procedure

```bash
# 1. Ensure all checklist items in docs/RELEASE_CHECKLIST.md are checked
# 2. Final regression pass
python -m pytest tests/ -q
cd frontend && npx tsc --noEmit

# 3. Merge to main
git checkout main
git merge --no-ff feature/P1-4-app-mode -m "Release v6.0.0 — ARGUS WorldView Transformation complete"
git tag v6.0.0

# 4. Build and push Docker image
docker build -t argus-intel:$(git rev-parse --short HEAD) .
docker push registry.example.com/argus-intel:$(git rev-parse --short HEAD)

# 5. Deploy
docker compose pull && docker compose up -d

# 6. Verify
curl http://localhost:8000/healthz        # → 200
curl http://localhost:8000/readyz         # → 200
curl http://localhost:8000/api/v1/health/connectors  # → 200
```

---

## Rollback Procedure

```bash
# Roll back to previous image
docker compose down
git checkout <previous-tag>
docker compose up -d

# Verify
curl http://localhost:8000/healthz
```

Full rollback procedure is documented in `docs/RUNBOOK.md` §3.
