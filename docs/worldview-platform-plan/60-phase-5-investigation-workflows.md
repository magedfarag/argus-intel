# Phase 5 — Investigation Workflows

## Objective

Turn the platform into a real analyst workstation with saved cases, evidence, alerts, and assisted reasoning.

## Exit criteria

- analysts can save investigations
- alerts/watchlists exist across entities and zones
- evidence packs include multi-layer provenance
- LLM assistance is bounded by explicit source grounding

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P5-1 | Create investigation domain models and persistence | `src/models/`, storage, APIs | `L1` + `L3` | `[ ]` | P4 gate | `P5-A` | Cases, notes, bookmarks, selected time windows |
| P5-2 | Expand evidence pack generation for all supported event families | `src/services/`, export paths | `L3` | `[ ]` | P5-1 | `P5-B` | Include imagery, telemetry, airspace, strike, and derived events |
| P5-3 | Implement watchlists and alert subscriptions | `src/services/`, frontend panels | `L3` + `L4` | `[ ]` | P5-1 | `P5-B` | Entity-based and AOI-based subscriptions |
| P5-4 | Add absence-as-signal analytics | `src/services/` | `L3` | `[ ]` | P1 gate | `P5-C` | AIS gaps, camera gaps, GPS quality drop windows |
| P5-5 | Build LLM-assisted briefing/query service with strict source grounding | service layer + frontend panel | `L0` + `L3` + `L4` | `[ ]` | P5-2, P5-4 | `P5-C` | No unsupported claims; source references required |
| P5-6 | Add investigation workspace UI | frontend panels and layouts | `L4` | `[ ]` | P5-1, P5-3 | `P5-D` | Case summary, evidence list, saved views |
| P5-7 | Add analyst QA/red-team review for claim quality | test protocol + fixtures | `L6` | `[ ]` | P5-5 | `P5-D` | Evaluate grounded answers and export quality |

## Parallel execution notes

- `P5-1` is the contract anchor for the rest of the phase.
- `P5-2`, `P5-3`, and `P5-4` can run in parallel once investigations exist.
- `P5-5` should not start before evidence and absence analytics are defined.

## Validation

- saved cases reopen with the correct time window, filters, and selected entities
- evidence packs are exportable and source-grounded
- LLM outputs cite only supported, stored facts

## Gate review

- [ ] Saved investigations work
- [ ] Alerts/watchlists work
- [ ] Evidence packs cover all major layer families
- [ ] Assisted briefing/query passes grounding review
