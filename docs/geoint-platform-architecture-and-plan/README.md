# Geospatial Intelligence Platform — Architecture and Delivery Baseline

This repository contains the architecture and phased delivery baseline for a multi-source geospatial intelligence platform focused on:

- construction activity monitoring
- satellite and aerial imagery analysis
- ship tracking
- air traffic tracking
- broader geospatial/event monitoring

The design priorities are:

- free/public sources first
- Middle East suitability first
- incremental delivery with production-ready releases at the end of each phase
- interoperability and normalization
- no premature overengineering

## What is in this package

- `docs/architecture.md` — target architecture, trade-offs, and recommended architecture choice
- `docs/delivery-plan.md` — milestone-based phased roadmap
- `docs/source-strategy.md` — classified source inventory and phased source recommendations
- `docs/canonical-event-model.md` — normalized event model
- `docs/release-phases.md` — release-by-release summary
- `docs/risk-register.md` — key risks, mitigations, and owners
- `docs/decision-log.md` — ADR-style decision log
- `docs/adr/` — individual ADR records
- `schemas/canonical-event.schema.json` — machine-readable starting schema
- `data/source_inventory_classified.csv` — spreadsheet-derived classified source inventory
- `config/example.env` — configuration placeholders only

## Recommended next step

After architecture approval, the recommended next implementation step is **Phase 1 only**:

1. stand up the 2D operational map,
2. implement AOI CRUD,
3. integrate STAC imagery search,
4. add basic timeline/event search,
5. validate three pilot AOIs in the Middle East.

Do **not** start with full streaming ingestion, full ML change analytics, or premium source integrations.

## Source basis

This baseline uses the uploaded `tracking_sources_inventory_middle_east.xlsx` as the candidate-source inventory and adds GDELT as a required contextual layer because it is part of the stated target architecture.

## Notes

This package is architecture-first. It intentionally does not implement the full product.
