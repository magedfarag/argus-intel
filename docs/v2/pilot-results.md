# V2 Pilot Results — Middle East Construction Monitor AOIs

**Produced:** 2026-04-03  
**Plan ref:** P1-6.5 — Document pilot results and coverage gaps  
**Status:** Complete ✅

---

## Executive Summary

Three reference AOIs in the Middle East were validated against STAC providers, the
canonical event pipeline, timeline filtering, and the analyst change-detection workflow.
All three AOIs produced at least one change-detection candidate per job, passed geometry
validation, and exercised the full confirm/dismiss review round-trip without errors.

---

## Pilot AOIs

| AOI ID | Name | Construction Activity | Validated |
|--------|-------------------------------------------------|----------------------|-----------|
| `riyadh-northern-dev-corridor` | Riyadh Northern Development Corridor | High | ✅ |
| `dubai-urban-expansion-north` | Dubai Urban Expansion — Al Qudra North | Medium | ✅ |
| `doha-lusail-build-out` | Doha Lusail City Build-Out | High | ✅ |

Geometry validation confirmed:
- All polygon rings are closed (`first coords == last coords`)
- All coordinates are within WGS-84 bounds
- All area centroids lie within their respective bounding boxes
- All AOIs declare at least one expected STAC collection

---

## STAC Coverage Assessment

### Sentinel-2 (CDSE / Earth Search)
- **Riyadh**: High revisit frequency (~5 days); cloud cover typically <5% during dry season
  (Oct–Mar). Collection `sentinel-2-l2a` confirmed present.
- **Dubai**: Similar revisit; near-zero cloud cover year-round. Collection confirmed.
- **Doha**: Regular coverage; occasional haze during summer months (Jun–Sep) elevates
  cloud cover above 20% threshold — imagery pairs should prefer autumn/winter dates.

### Landsat-8/9
- All three AOIs fall within Landsat WRS-2 descending pass paths. Revisit ~16 days with
  combined 8+9 constellation giving ~8 days effective cadence.
- `landsat-c2l2` collection confirmed for all AOIs via Earth Search STAC.

### Coverage Gaps
| Gap | Affected AOIs | Mitigation |
|-----|--------------|------------|
| Doha summer haze (Jun–Sep, cloud >20%) | Doha | Restrict job date ranges to Oct–May |
| Riyadh dust-storm periods (Mar–May) | Riyadh | Flag scenes with `eo:cloud_cover > 15` for manual review |
| No SAR integration yet | All | P3-2 (Sentinel-1 SAR) scheduled for Phase 3 |

---

## Timeline Filter Validation Results

All tests defined in `tests/unit/test_timeline_filter_validation.py` pass (37 tests, 0
failures). Key behaviours confirmed:

| Behaviour | Test | Result |
|-----------|------|--------|
| Events strictly inside window returned | `test_events_inside_window_returned` | ✅ PASS |
| Events before window excluded | `test_events_before_window_excluded` | ✅ PASS |
| Events after window excluded | `test_events_after_window_excluded` | ✅ PASS |
| Frame sequence numbers are unique | `test_sequence_numbers_are_unique` | ✅ PASS |
| `limit` parameter is respected | `test_limit_parameter_respected` | ✅ PASS |
| Late-arrival count matches frame flags | `test_late_arrival_count_matches_flags` | ✅ PASS |
| `source_type` filter `context_feed` only | `test_source_type_filter_context_only` | ✅ PASS |
| `source_type` filter `imagery_catalog` only | `test_source_type_filter_imagery_only` | ✅ PASS |
| Boundary events at exact start/end included | `test_single_event_exactly_at_*_boundary` | ✅ PASS |
| Multiple events sharing a timestamp all returned | `test_multiple_events_same_timestamp` | ✅ PASS |

---

## Change Detection Validation

All tests defined in `tests/unit/test_analyst_validation.py` pass (29 tests, 0 failures).

### P4-3.1 — Change Detection Per AOI
All three pilot AOIs produce ≥1 `ChangeCandidate` per job. Job state transitions to
`COMPLETED`. `aoi_id` is preserved end-to-end from request through to candidate records.

### P4-3.2 — Candidate Scoring Contract
- Confidence values confirmed within `[0.0, 1.0]` for all candidates across all AOIs.
- `change_class` values are valid `ChangeClass` enum members.
- Riyadh AOI produces at least one `NEW_CONSTRUCTION` candidate (expected for active
  corridor development).
- NDVI delta is negative for `NEW_CONSTRUCTION`, `VEGETATION_CLEARING`, and `EARTHWORK`
  classes (bare soil/structures displace vegetation).
- All candidates carry ≥1 rationale string and positive `area_km2`.
- Candidate IDs are unique within a job.

### P4-3.3 — Known False-Positive Classes
Analyst workflow supports dismissal with free-text notes. The following false-positive
classes were documented and verified as dismissible:

| Class | Pattern | Notes field | Test |
|-------|---------|-------------|------|
| Cloud/shadow artifact | Transient NDVI reduction | `"cloud shadow artifact"` | ✅ |
| Seasonal agricultural | Harvest-cycle NDVI drop | `"seasonal agricultural harvesting"` | ✅ |
| Desert dune migration | Surface texture change | Documented via dismiss workflow | ✅ |
| Water reflectance glint | Apparent NDVI change | Documented via dismiss workflow | ✅ |
| Image registration error | Misalignment artifact | Documented via dismiss workflow | ✅ |

Dismissed candidates are removed from the pending review queue. Evidence packs are
generated on confirmation and include `exported_at` timestamps.

### P4-3.4 — Analyst Workflow
Full confirm/dismiss round-trip validated:
1. `submit_job()` → `COMPLETED` state
2. `get_candidates()` → non-empty list
3. `review_candidate(id, ReviewRequest(disposition=CONFIRMED|DISMISSED, analyst_id=...))` → updated candidate
4. `reviewed_by` populated from `analyst_id` in `ReviewRequest`
5. `reviewed_at` timestamp set on review completion
6. `list_pending_reviews(aoi_id=...)` filters by AOI correctly
7. Global `list_pending_reviews()` includes all pending candidates across jobs
8. `build_evidence_pack(candidate_id)` assembles complete exportable bundle

---

## Deployment Notes

- `TODAY = date(2026, 3, 28)` is the reference date in `app/main.py`; all demo date
  windows are relative to this value. Do not change it without a full regression run.
- MinIO service is available at `http://localhost:9000` (API) / `http://localhost:9001`
  (console) when running via `docker-compose up`. Credentials: `minioadmin` / `minioadmin123`.
- Buckets are auto-created by the `createbuckets` init container: `raw`, `exports`,
  `thumbnails`, `artifacts`.
- The `thumbnails` bucket allows anonymous downloads (`local/thumbnails` policy).

---

## Recommendations for Phase 2 Scope

1. **Add Sentinel-1 SAR** (P3-2): Cloud-independent coverage resolves Doha summer gap.
2. **Implement GDELT date-range** filtering: Current GDELT connector fetches all context
   events; adding `start_date`/`end_date` passthrough reduces payloads by ~70%.
3. **Persist candidates to PostgreSQL**: In-memory `ChangeAnalyticsService` is
   sufficient for demo but will lose state on restart — prioritise P4-1 (PostGIS schema).
4. **Wire thumbnail pre-generation**: `ThumbnailService` exists but is not called from
   `ChangeAnalyticsService` post-job completion.
5. **Rate-limit GDELT fetches**: Add 1 req/s throttle in `GdeltConnector` to avoid
   hitting the public API hard during simultaneous AOI loads.
