"""P1-6.1: Three Middle East pilot AOIs used for STAC search validation.

These AOIs are canonical reference geometries for:
- Verifying STAC imagery coverage (P1-6.2)
- Timeline filter correctness tests (P1-6.3)
- Map performance benchmarks (P1-6.4)

Each AOI is a GeoJSON Polygon (approx. 5×5 km bbox) centred on an active
construction zone in a Middle East city with known Sentinel-2 coverage.
"""
from __future__ import annotations
from typing import Any, Dict, List


# ── Pilot AOI definitions ────────────────────────────────────────────────────

PILOT_AOIS: List[Dict[str, Any]] = [
    {
        "id": "pilot-riyadh-neom-northgate",
        "name": "Riyadh — Northern Development Corridor",
        "description": (
            "5×5 km area north of Riyadh city centre near King Salman Road.  "
            "Active large-scale infrastructure and residential development.  "
            "Sentinel-2 revisit: ~5 days; expected cloud cover <10% (Nov–Apr)."
        ),
        "country": "Saudi Arabia",
        "city": "Riyadh",
        "centroid": {"lon": 46.6753, "lat": 24.8000},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [46.6528, 24.7775],
                [46.6978, 24.7775],
                [46.6978, 24.8225],
                [46.6528, 24.8225],
                [46.6528, 24.7775],
            ]],
        },
        "expected_stac_collections": ["sentinel-2-l2a", "landsat-c2-l2"],
        "construction_activity": "high",
        "notes": "Part of Riyadh Vision 2030 urban expansion programme.",
    },
    {
        "id": "pilot-dubai-creek-harbour",
        "name": "Dubai — Creek Harbour Development",
        "description": (
            "5×5 km area around Dubai Creek Harbour reclamation and tower project.  "
            "Continuous sea-front and mixed-use construction.  "
            "Sentinel-2 revisit: ~5 days; cloud cover typically <5% year-round."
        ),
        "country": "UAE",
        "city": "Dubai",
        "centroid": {"lon": 55.3500, "lat": 25.2048},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [55.3275, 24.9823],
                [55.3725, 24.9823],
                [55.3725, 25.2273],
                [55.3275, 25.2273],
                [55.3275, 24.9823],
            ]],
        },
        "expected_stac_collections": ["sentinel-2-l2a", "landsat-c2-l2"],
        "construction_activity": "high",
        "notes": "Dubai Creek Tower site; waterfront reclamation ongoing as of 2026.",
    },
    {
        "id": "pilot-doha-lusail-city",
        "name": "Doha — Lusail City North",
        "description": (
            "5×5 km area in Lusail planned city, northern Doha.  "
            "Large-scale mixed-use development visible in recent EO imagery.  "
            "Sentinel-2 revisit: ~5 days; cloud cover <5% year-round."
        ),
        "country": "Qatar",
        "city": "Doha",
        "centroid": {"lon": 51.5100, "lat": 25.4200},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [51.4875, 25.3975],
                [51.5325, 25.3975],
                [51.5325, 25.4425],
                [51.4875, 25.4425],
                [51.4875, 25.3975],
            ]],
        },
        "expected_stac_collections": ["sentinel-2-l2a", "landsat-c2-l2"],
        "construction_activity": "high",
        "notes": "Post-World-Cup legacy infrastructure build-out.",
    },
]


def get_pilot_aoi(aoi_id: str) -> Dict[str, Any]:
    """Return a pilot AOI by id, raising KeyError if not found."""
    for aoi in PILOT_AOIS:
        if aoi["id"] == aoi_id:
            return aoi
    raise KeyError(f"Pilot AOI not found: {aoi_id!r}")
