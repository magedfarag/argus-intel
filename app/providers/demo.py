"""DemoProvider — returns deterministic curated sample detections.

This preserves the original demo behaviour exactly while conforming to the
SatelliteProvider interface.  It is always available (no credentials needed)
and is used as the final fallback when live providers are unavailable.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.scene import SceneMetadata
from app.providers.base import SatelliteProvider

# ── Demo dataset anchor ───────────────────────────────────────────────────
TODAY         = date(2026, 3, 28)
MIN_AREA_KM2  = 0.01
MAX_AREA_KM2  = 100.0
MAX_LOOKBACK  = 30
ASSETS_PREFIX = "/static/assets"

# ── Curated scenarios ─────────────────────────────────────────────────────
SCENARIOS = [
    {
        "template_id":  "chg-site-clearing",
        "change_type":  "Site clearing / earthwork",
        "day_offset":   5,
        "confidence":   0.86,
        "summary":      "Bare-soil expansion and surface scraping pattern indicate recent site clearing.",
        "rationale": [
            "Strong reduction in green cover within selected footprint",
            "Linear scrape marks and cleared pad visible in after image",
            "Shape and texture are inconsistent with normal seasonal vegetation shift",
        ],
        "before_image": "site_clearing_before.png",
        "after_image":  "site_clearing_after.png",
    },
    {
        "template_id":  "chg-foundation",
        "change_type":  "Foundation work",
        "day_offset":   12,
        "confidence":   0.91,
        "summary":      "New slab-like reflective surfaces and regular footprint suggest foundation installation.",
        "rationale": [
            "Rectilinear footprint emerged after excavation stage",
            "High reflectance and consistent edges resemble poured concrete",
            "Context is spatially consistent with active construction rather than demolition",
        ],
        "before_image": "foundation_before.png",
        "after_image":  "foundation_after.png",
    },
    {
        "template_id":  "chg-roofing",
        "change_type":  "Roofing / enclosure",
        "day_offset":   21,
        "confidence":   0.93,
        "summary":      "A completed roof plane and enclosed footprint indicate structural completion progress.",
        "rationale": [
            "Distinct roof polygon appeared where framing only was previously visible",
            "Object edges are stable across footprint and not attributable to cloud shadow",
            "Spectral contrast indicates material installation rather than bare ground change",
        ],
        "before_image": "roofing_before.png",
        "after_image":  "roofing_after.png",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────

def _polygon_area_km2(coords: List[List[float]]) -> float:
    if len(coords) < 4:
        raise ValueError("Polygon must contain at least 4 coordinates")
    lat0 = math.radians(sum(lat for _, lat in coords) / len(coords))
    mpd_lat = 111132.92
    mpd_lon = 111412.84 * math.cos(lat0)
    proj = [(lng * mpd_lon, lat * mpd_lat) for lng, lat in coords]
    area = 0.0
    for i in range(len(proj) - 1):
        x1, y1 = proj[i]
        x2, y2 = proj[i + 1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0 / 1_000_000.0


def _interpolate(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# ── Provider implementation ───────────────────────────────────────────────

class DemoProvider(SatelliteProvider):
    provider_name = "demo"
    display_name  = "Demo (synthetic data)"
    resolution_m  = 10  # representative

    def validate_credentials(self) -> Tuple[bool, str]:
        return True, "Demo provider requires no credentials"

    def healthcheck(self) -> Tuple[bool, str]:
        return True, "Demo provider is always healthy"

    def get_capabilities(self) -> Dict[str, Any]:
        caps = super().get_capabilities()
        caps.update({"requires_credentials": False, "is_demo": True})
        return caps

    def search_imagery(
        self,
        geometry: Dict[str, Any],
        start_date: str,
        end_date: str,
        cloud_threshold: float = 20.0,
        max_results: int = 10,
    ) -> List[SceneMetadata]:
        # Demo returns two synthetic scenes flanking the analysis window.
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
        mid = sd + timedelta(days=(ed - sd).days // 2)
        return [
            SceneMetadata(
                scene_id=f"demo-before-{sd.isoformat()}",
                provider="demo",
                satellite="Sentinel-2 (synthetic)",
                acquired_at=datetime.combine(sd + timedelta(days=1), datetime.min.time()),
                cloud_cover=0.0,
                bbox=[-180, -90, 180, 90],
            ),
            SceneMetadata(
                scene_id=f"demo-after-{ed.isoformat()}",
                provider="demo",
                satellite="Sentinel-2 (synthetic)",
                acquired_at=datetime.combine(ed, datetime.min.time()),
                cloud_cover=0.0,
                bbox=[-180, -90, 180, 90],
            ),
        ]

    def fetch_scene_metadata(self, scene_id: str) -> Optional[SceneMetadata]:
        return SceneMetadata(
            scene_id=scene_id,
            provider="demo",
            satellite="Sentinel-2 (synthetic)",
            acquired_at=datetime.now(timezone.utc),
            cloud_cover=0.0,
            bbox=[-180, -90, 180, 90],
        )

    # ── Core demo analysis logic kept as in original main.py ──────────────

    def generate_changes(
        self,
        bounds: List[float],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Return curated change records for the requested window."""
        min_lng, min_lat, max_lng, max_lat = bounds
        width  = max(max_lng - min_lng, 0.0001)
        height = max(max_lat - min_lat, 0.0001)

        changes = []
        for idx, scenario in enumerate(SCENARIOS):
            detected_day = TODAY - timedelta(days=scenario["day_offset"])
            if not (start_date <= detected_day <= end_date):
                continue
            fx = 0.22 + idx * 0.23
            fy = 0.30 + idx * 0.18
            cx = _interpolate(min_lng, max_lng, fx)
            cy = _interpolate(min_lat, max_lat, fy)
            hw = width * 0.09
            hh = height * 0.08
            changes.append({
                "change_id":    f"{scenario["template_id"]}-{idx + 1}",
                "detected_at":  datetime.combine(
                    detected_day, datetime.min.time()
                ).replace(hour=10 + idx * 2, minute=30),
                "change_type":  scenario["change_type"],
                "confidence":   round(scenario["confidence"] * 100, 1),
                "center":       {"lng": round(cx, 6), "lat": round(cy, 6)},
                "bbox":         [round(v, 6) for v in [cx - hw, cy - hh, cx + hw, cy + hh]],
                "provider":     "demo",
                "summary":      scenario["summary"],
                "rationale":    scenario["rationale"],
                "before_image": f"{ASSETS_PREFIX}/{scenario["before_image"]}",
                "after_image":  f"{ASSETS_PREFIX}/{scenario["after_image"]}",
                "thumbnail":    f"{ASSETS_PREFIX}/{scenario["after_image"]}",
                "is_demo":      True,
            })
        return changes
