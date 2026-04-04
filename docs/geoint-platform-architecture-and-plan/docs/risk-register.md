# Risk Register

| ID | Risk | Category | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|---|
| R-001 | Middle East public-record data is sparse or absent for target AOIs | Data availability | High | High | Treat public records as opportunistic; make imagery/context the backbone; validate pilot AOIs before promises | Product + Data |
| R-002 | Free/public imagery resolution is insufficient for small construction sites | Data suitability | High | High | Position public imagery as broad-area monitoring; preserve upgrade seam for premium imagery | Product |
| R-003 | Community AIS/ADS-B coverage is uneven by country | Coverage | Medium | High | Bound initial AOIs; expose coverage caveats; compare multiple feeds before escalation | Data |
| R-004 | Licensing/redistribution violations occur when mixing sources in exports | Compliance | Medium | High | Persist license metadata per source/event; enforce export filters; legal review before production | Product + Engineering |
| R-005 | Dense moving-object feeds overwhelm browser rendering | Performance | High | High | Viewport filtering, server simplification, zoom gating, TripsLayer limits, bounded windows | Frontend |
| R-006 | Playback interpolates sparse data and misleads analysts | Analytical correctness | Medium | High | Mark interpolated segments explicitly; disable interpolation by default for sparse feeds | Analytics |
| R-007 | Source APIs change or public services throttle/break | Operational dependency | High | Medium | Adapter isolation, health checks, retries, fallback sources, local caches where allowed | Platform |
| R-008 | Team overbuilds infrastructure before validating workflows | Delivery | High | High | Phase gating, ADR discipline, thin vertical slices, explicit deferrals | Leadership |
| R-009 | GDELT/news context introduces noise or bias | Data quality | Medium | Medium | Treat as contextual only; never authoritative; provide source attribution and toggles | Product |
| R-010 | Canonical event model becomes bloated by source-specific exceptions | Architecture | Medium | Medium | Keep common core narrow; move specifics into `attributes`; ADR for schema changes | Architecture |
| R-011 | Public geocoding/routing endpoints are unsuitable for production scale | Operational dependency | Medium | Medium | Self-host OSM services or add commercial geocoder only when needed | Platform |
| R-012 | Change analytics is pushed before imagery and replay quality are stable | Product risk | Medium | High | Gate Phase 4 on analyst validation in Phases 1–3 | Product |
