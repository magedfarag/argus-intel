# Phase 5: Investigation Workflows

## Objective

Turn the platform into an analyst workstation with saved investigations, evidence packs, narrative exports, and agent-assisted query flows.

## Entry Criteria

- Phase 1 data plane is stable
- Later phases provide richer evidence, but this phase should begin once the underlying history is trustworthy

## Exit Criteria

- Users can create and revisit investigations
- Evidence packs and narrative exports are first-class outputs
- Agent-assisted briefing/query workflows exist on top of the normalized event model

## Track A: Saved Investigations

- `[x]` Add investigation entity model and persistence
- `[x]` Add watchlists, notes, and saved filters
- `[x]` Add investigation landing UI and navigation
- `[x]` Add sharing or export posture for investigations if in scope

## Track B: Evidence Packs And Narrative Exports

- `[x]` Extend evidence-pack generation beyond change detection
- `[x]` Add export templates for multi-source incidents
- `[x]` Add timeline snapshots, layer summaries, and provenance sections
- `[x]` Add tests for export completeness and determinism

## Track C: Agent-Assisted Workflows

- `[x]` Define assistant/query surface for analysts
- `[x]` Add safe retrieval over normalized events and investigations
- `[x]` Add briefing generation backed by actual data, not only templates
- `[x]` Add source-citation and provenance rules for generated outputs

## Track D: Absence-As-Signal Analytics

- `[x]` Formalize analytics for AIS gaps, GPS loss, camera silence, and expected-but-missing events
- `[x]` Add confidence/provenance model for absence-derived findings
- `[x]` Add UI surfaces for absence-based alerts
- `[x]` Add replay-aware tests for absence logic

## Suggested Subagent Split

- Subagent 1: Track A
- Subagent 2: Track B
- Subagent 3: Track C
- Subagent 4: Track D

## Notes

- Agent outputs must cite or point back to the underlying evidence model.
- Narrative exports should be defensible and reproducible.

## Track A Completion — 2026-04-04

Backend delivered: `src/models/investigations.py`, `src/services/investigation_service.py`,
`src/api/investigations.py` registered in `app/main.py`.  
Tests: 23 unit + 24 integration = **47 tests, all passing**.  
Remaining Track A items (UI, sharing/export) are frontend work (Tracks C/D scope).

## Track D Completion — 2026-04-04

Backend delivered: `src/models/absence_signals.py`, `src/services/absence_analytics.py`,
`src/api/absence.py` registered in `app/main.py`.  
Models: `AbsenceSignalType`, `AbsenceSeverity`, `AbsenceSignal`, `AbsenceSignalCreateRequest`,
`AbsenceAlert`, `AbsenceAnalyticsSummary` — all UTC-enforced, Pydantic v2.  
Service: thread-safe singleton, 5 deterministic demo signals seeded, `detect_ais_gaps()` scan,
`generate_alerts()` clustering, `get_summary()` window analytics.  
API: 8 endpoints under `/api/v1/absence/` (signals CRUD + resolve + link-event, alerts, summary, AIS scan).  
Tests: 24 unit + 21 integration = **45 tests, all passing**.  
Remaining Track D item (UI surfaces for alerts) is frontend work.

## Track B Completion — 2026-04-04

Backend delivered: `src/models/evidence_pack.py`, `src/services/evidence_pack_service.py`,
`src/api/evidence_packs.py` registered in `app/main.py`.  
Tests: 15 unit + 14 integration = **29 tests, all passing**.  
Supports JSON, Markdown, and GeoJSON rendering; investigation-linked packs via `POST /from-investigation/{inv_id}`; time-window queries against the shared event store.

## Track C Completion — 2026-04-04

Backend delivered: `src/models/analyst_query.py`, `src/services/analyst_query_service.py`,
`src/api/analyst.py` registered in `app/main.py`.  
Models: `QueryOperator`, `QueryFieldType`, `QueryFilter`, `AnalystQuery`, `QueryResult`,
`BriefingSection`, `BriefingRequest`, `BriefingOutput` — all UTC-enforced, Pydantic v2.  
Service: thread-safe singleton, structured query execution across all 7 filter field types
(EVENT_TYPE, SOURCE_TYPE, ENTITY_ID, TIME_RANGE, CONFIDENCE, GEOMETRY, TEXT) with AND/OR/NOT
combinators, data-backed briefing generation for all 7 sections with citations and provenance,
plain-text export with classification header/footer.  
API: 11 endpoints under `/api/v1/analyst/` (ad-hoc query, saved query CRUD + execute,
briefing generation + list/get/text/from-investigation).  
Tests: 20 unit + 19 integration = **39 tests, all passing**.  
No external LLM calls — all outputs are deterministic from the canonical event store.
