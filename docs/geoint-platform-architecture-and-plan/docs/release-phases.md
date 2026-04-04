# Release Phases

This document summarizes the production intent of each release phase.

## Phase 0 — Foundation and architecture
**Release intent:** internal baseline  
**Primary deliverables:** architecture docs, source strategy, event model, ADRs, scaffolding, risk register  
**Client visibility:** roadmap and architecture walkthrough  
**Acceptance:** architecture and phase plan approved

## Phase 1 — MVP operational map
**Release intent:** first client-usable pilot  
**Primary deliverables:** 2D map, AOI workflows, source catalog, STAC imagery search, basic timeline  
**Client visibility:** usable operational demo on real AOIs  
**Acceptance:** analyst can search and export AOI results

## Phase 2 — Imagery and context
**Release intent:** analytical pilot+  
**Primary deliverables:** historical replay, imagery/context timeline, GDELT enrichment, offline export packs  
**Client visibility:** replayed 30-day AOI analysis  
**Acceptance:** imagery and contextual events are synchronized and exportable

## Phase 3 — Maritime and aviation
**Release intent:** operational beta  
**Primary deliverables:** ship and aircraft connectors, track playback, dense-layer controls  
**Client visibility:** sample-video-style movement playback within bounded AOIs  
**Acceptance:** stable playback under agreed density limits

## Phase 4 — Change analytics
**Release intent:** limited production  
**Primary deliverables:** change jobs, scoring, analyst review, evidence packs  
**Client visibility:** actual construction-change workflow  
**Acceptance:** analysts can disposition results and export evidence

## Phase 5 — Production hardening
**Release intent:** production  
**Primary deliverables:** caching, async jobs, resilience, release management, source health dashboards  
**Client visibility:** stable operational service  
**Acceptance:** performance, rollback, monitoring, and runbooks validated

## Optional / premium track
The following remain optional until a proven business case exists:
- commercial high-resolution imagery and SAR
- premium vessel and aviation providers
- advanced ML change models
- multi-tenant enterprise controls
- large-scale historical warehouse
