# ADR-002 — STAC-first imagery interoperability

## Status
Accepted

## Context
Imagery catalogs differ by provider, but STAC is the strongest common discovery abstraction available across public catalogs and many commercial platforms.

## Decision
Use STAC as the default discovery abstraction for imagery. Start with Copernicus Data Space Ecosystem and Earth Search. Preserve the ability to add other STAC or STAC-like providers later.

## Consequences
- Faster imagery integration.
- Less provider lock-in.
- Some provider-specific functionality remains outside the abstraction.
