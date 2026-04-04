# ARGUS — Maritime Intelligence Transformation Plan
## Status Tracker

**Created:** 2026-04-04
**Updated:** 2026-04-05
**Target:** God''s Eye maritime intelligence platform (oil tanker tracking, dark ships, chokepoint analytics)

---

## Phase 1 — Backend Data Layer
| Task | File | Status |
|------|------|--------|
| P6-1 Chokepoint polygons + metrics service | src/services/chokepoint_service.py | [x] |
| P6-1 Chokepoint REST API | src/api/chokepoints.py | [x] |
| P6-2 Vessel registry (sanctioned/IRGC/clean) | src/services/vessel_registry.py | [x] |
| P6-2 Vessel lookup API | src/api/vessels.py | [x] |
| P6-3 Extend canonical_event.py (DARK_SHIP_CANDIDATE) | src/models/canonical_event.py | [x] |
| P6-3 Dark ship demo data in seeder | src/services/demo_seeder.py | [x] |

## Phase 2 — Dark Ship Detection
| Task | File | Status |
|------|------|--------|
| P6-4 Dark ship detector service | src/services/dark_ship_detector.py | [x] |
| P6-5 Dark ship REST API | src/api/dark_ships.py | [x] |

## Phase 3 — Intelligence Briefing
| Task | File | Status |
|------|------|--------|
| P6-6 Intel briefing generator | src/services/intel_briefing.py | [x] |
| P6-6 Intel briefing API | src/api/intel.py | [x] |
| P6-6 Register new routers in main.py | app/main.py | [x] |

## Phase 4 — Frontend
| Task | File | Status |
|------|------|--------|
| P6-7 God''s Eye entry animation | frontend/src/components/GlobeView/GlobeView.tsx | [x] |
| P6-8 Chokepoint overlay layer on globe | frontend/src/components/GlobeView/GlobeView.tsx | [x] |
| P6-9 Dark ship pulsing circles on globe | frontend/src/components/GlobeView/GlobeView.tsx | [x] |
| P6-10 Chokepoint panel | frontend/src/components/ChokepointPanel/ | [x] |
| P6-11 Dark ship panel | frontend/src/components/DarkShipPanel/ | [x] |
| P6-12 Intelligence briefing panel | frontend/src/components/IntelBriefingPanel/ | [x] |
| P6-13 Vessel profile modal | frontend/src/components/VesselProfileModal/ | [x] |
| P6-14 Bottom chokepoint metrics bar | frontend/src/components/ChokeMetricsBar/ | [x] |
| P6-15 Maritime API types + client | frontend/src/api/types.ts + client.ts | [x] |
| P6-16 Wire new panels into App.tsx | frontend/src/App.tsx | [x] |
| P6-17 New CSS styles | frontend/src/App.css | [x] |

## Phase 5 — Rebrand
| Task | File | Status |
|------|------|--------|
| P6-18 Title / subtitle update | frontend/src/App.tsx | [x] |
| P6-19 Default view mode 3D | frontend/src/App.tsx | [x] |
| P6-20 Pilot AOIs -> Hormuz/Bab-el-Mandeb | src/services/demo_seeder.py | [x] |

---

## Progress
- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] Phase 5 complete
