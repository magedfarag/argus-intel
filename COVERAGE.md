# Test Coverage Report

**Generated:** 2026-04-04 (Batch 2026-04-04c)
**Suite:** unit tests only (`tests/unit/`)
**Packages measured:** `app/` + `src/`

## Summary

| Metric | Value |
|--------|-------|
| Unit tests passing | 738 |
| Unit tests skipped | 3 |
| Integration tests passing | 39 |
| Integration tests skipped | 11 |
| **Total passing** | **777** |
| **Total skipped** | **14** |
| Overall line coverage | **71%** |
| Statements covered | 3 856 / 5 408 |

## How to regenerate

```bash
python -m pytest tests/unit/ \
  --cov=app --cov=src \
  --cov-report=term-missing \
  --cov-report=html:htmlcov \
  -q
```

HTML report is written to `htmlcov/index.html` (git-ignored).

## CI coverage gate

The CI pipeline (`ci.yml`) enforces `--cov-fail-under=20` as a safety floor.
Coverage HTML is uploaded as a GitHub Actions artifact (`coverage-report-<app_mode>`)
for each matrix run (`demo` / `staging` / `production`).

## Module coverage highlights

| Module | Coverage |
|--------|---------|
| `src/models/analytics.py` | 100% |
| `src/models/aoi.py` | 100% |
| `src/models/compare.py` | 100% |
| `src/models/event_search.py` | 100% |
| `src/services/aoi_store.py` | 100% |
| `src/connectors/gdelt.py` | 97% |
| `src/services/telemetry_store.py` | 98% |
| `src/models/canonical_event.py` | 99% |
| `app/resilience/circuit_breaker.py` | 97% |
| `src/storage/database.py` | 0% (requires live PostGIS — skipped in CI) |
| `src/storage/models.py` | 0% (requires live PostGIS — skipped in CI) |

> **Note:** `src/storage/` is intentionally 0% in unit tests.
> Integration coverage is obtained when a live PostGIS instance is available.
> See `tests/integration/test_db_schema.py` (4 tests, skipped without DB).
