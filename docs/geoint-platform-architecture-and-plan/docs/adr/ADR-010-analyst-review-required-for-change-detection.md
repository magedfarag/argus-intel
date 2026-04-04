# ADR-010 — Construction-change analytics requires analyst review

## Status
Accepted

## Context
The change detection pipeline computes NDVI delta scores from before/after Sentinel-2 imagery pairs. The scores are informative but imprecise: cloud cover, seasonal vegetation change, SAR artifacts, and illumination differences all generate false positives. An automated "construction activity confirmed" verdict based on NDVI delta alone would introduce unacceptable noise into analyst workflows.

## Decision
1. **No automated production verdicts.** All change candidates require analyst disposition (`confirmed` / `dismissed`) via the review workflow before they become part of the project record.
2. **Confidence scores are advisory only.** The `ChangeCandidate.confidence` field informs but does not replace analyst judgment.
3. **Known false-positive classes must be documented** for each release and surfaced in the analyst review UI.
4. **Phase 4 is gated on Phase 1–3 validation.** Change detection cannot be promoted to any production workflow before STAC imagery search, timeline replay, and analyst review have been validated on pilot AOIs.

## Consequences
- `src/api/analytics.py` exposes `PUT /api/v1/analytics/change-detection/{id}/review` with `analyst_id`, `verdict`, `notes`, and `reviewed_at`.
- `AnalyticsPanel.tsx` surfaces pending candidates with before/after metadata and a confirm/dismiss control.
- Evidence packs (`GET /api/v1/analytics/change-detection/{id}/evidence-pack`) bundle analyst notes, imagery metadata, and correlated context events for audit.
- `tests/unit/test_analyst_validation.py` (29 tests) validates precision/recall behaviour against ground-truth fixture data.
- False-positive classes documented: cloud shadow, seasonal NDVI change, SAR speckling, urban heat island contrast. See `docs/v2/pilot-results.md`.

## Implementation notes
- `src/services/change_analytics.py` — synthetic + rasterio pipeline with confidence scoring
- `src/api/analytics.py` — full review workflow API (submit, list candidates, review, evidence-pack)
- `frontend/src/components/AnalyticsPanel/AnalyticsPanel.tsx` — review queue UI
- `tests/unit/test_change_analytics.py` — 48 tests covering job lifecycle + review workflow
