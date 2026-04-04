# Phase 6 — Hardening

## Objective

Make the platform supportable in pilot and production environments.

## Exit criteria

- auth and authorization are enforced
- performance, caching, and materialization are validated
- retention and cost controls are in place
- operational runbooks and rollback paths exist

## Task tracker

| ID | Task | Primary areas | Lane | Status | Depends on | Parallel pack | Notes |
|---|---|---|---|---|---|---|---|
| P6-1 | Implement auth, RBAC, and audit logging | API, storage, middleware | `L3` + `L6` | `[ ]` | P5 gate | `P6-A` | Pilot-safe minimum before production exposure |
| P6-2 | Add caching and materialization for heavy replay and 3D scene queries | `src/services/`, cache layer | `L1` + `L3` | `[ ]` | P3, P4 | `P6-B` | Hot windows, tile/frame materialization, invalidation strategy |
| P6-3 | Implement retention and provider-governance controls | storage, policy, docs | `L1` + `L6` | `[ ]` | P1 gate | `P6-C` | Snapshot TTLs, export policy, source restrictions |
| P6-4 | Add load, soak, and failover validation | tests, CI, runbooks | `L6` | `[ ]` | P6-1, P6-2 | `P6-B` | Include dense timeline playback and degraded provider scenarios |
| P6-5 | Add cost controls and observability for premium-capable future sources | config, dashboards | `L6` | `[ ]` | P6-3 | `P6-C` | Required before any premium expansion |
| P6-6 | Publish runbooks, rollback, and on-call docs | `docs/`, ops scripts | `L6` | `[ ]` | P6-4 | `P6-D` | Handover-quality operational docs |
| P6-7 | Conduct pilot go/no-go review | plan docs + checklist | `L0` + `L6` | `[ ]` | P6-1 through P6-6 | `P6-D` | Formal release decision gate |

## Parallel execution notes

- `P6-1`, `P6-2`, and `P6-3` can proceed together once Phase 5 is stable.
- `P6-4` should start as soon as auth and caching are functional, not at the very end.

## Validation

- auth/rbac tests pass
- replay and scene performance meet agreed budgets
- retention and export controls behave predictably
- on-call documentation is usable by someone other than the implementer

## Gate review

- [ ] Auth and audit controls are enforced
- [ ] Performance and failover tests pass
- [ ] Retention and governance controls are live
- [ ] Runbooks and rollback procedures are complete
- [ ] Pilot/production go-live approved
