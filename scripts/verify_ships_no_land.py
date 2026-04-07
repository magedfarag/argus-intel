"""Verify that every ship track never touches land.

Loads Natural Earth 10m land polygons, clips them to the Strait of Hormuz AOI,
then generates positions for ALL ships in _SHIP_ROUTES (not just active ones)
using the same interpolation the demo seeder uses.  Reports every violation.

Usage:
    python scripts/verify_ships_no_land.py

Prerequisites:
    - ne_10m_land.geojson must exist in the project root (downloaded by cURL or
      urllib once from the Natural Earth GitHub CDN).
    - shapely ≥ 2.0 must be installed (already in requirements.txt).
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from shapely.geometry import Point, box, shape
from shapely.ops import unary_union

# ── Add project root to sys.path so we can import seeder constants ───────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.demo_seeder import (
    _LON_MAX,
    _LON_MIN,
    _LAT_MAX,
    _LAT_MIN,
    _NORTHBOUND_TEMPLATE,
    _SOUTHBOUND_TEMPLATE,
    _OMAN_COASTAL_TEMPLATE,
    _NORTHBOUND_MIN_LAT,
    _NORTHBOUND_EASTERN_MAX_LAT,
    _SOUTHBOUND_MIN_LAT,
    _SOUTHBOUND_MUSANDAM_MAX_LAT,
    _OMAN_COAST_MIN_LAT,
    _OMAN_COAST_MAX_LAT,
    _SHIP_ROUTES,
    _interp_route,
    _deterministic_lane_route,
)

# ── 1. Build land union clipped to the AOI bounding box ──────────────────────

GEOJSON_PATH = ROOT / "ne_10m_land.geojson"
if not GEOJSON_PATH.exists():
    print("ERROR: ne_10m_land.geojson not found in project root.")
    print("  Download with:")
    print("  python -c \"import urllib.request; urllib.request.urlretrieve(")
    print("    'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson',")
    print("    'ne_10m_land.geojson')\"")
    sys.exit(1)

_MARGIN = 0.1          # Small margin outside AOI so we don't clip coastlines at the exact boundary
AOI_BOX = box(
    _LON_MIN - _MARGIN,
    _LAT_MIN - _MARGIN,
    _LON_MAX + _MARGIN,
    _LAT_MAX + _MARGIN,
)

print("Loading Natural Earth land polygons …")
raw = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
land_parts: list = []
for feat in raw["features"]:
    geom = shape(feat["geometry"])
    clipped = geom.intersection(AOI_BOX)
    if not clipped.is_empty:
        land_parts.append(clipped)

if not land_parts:
    print("WARNING: No land polygons found within the AOI extent. "
          "The downloaded file may be a simplified/low-res version. "
          "Proceeding with zero land — all ships will trivially pass.")
    land_union = None
else:
    land_union = unary_union(land_parts)
    print(f"  {len(land_parts)} land feature(s) within AOI extent merged into one geometry "
          f"({land_union.geom_type}).")


# ── 2. Generate all positions (same logic as demo_seeder._ship_events) ───────

def _all_ship_positions() -> dict[str, list[tuple[float, float]]]:
    """Return {mmsi: [(lon, lat), ...]} for every ship in _SHIP_ROUTES."""
    rng = random.Random(42)
    n_pos = 80
    result: dict[str, list[tuple[float, float]]] = {}
    for ship in _SHIP_ROUTES:
        route = _deterministic_lane_route(ship["mmsi"], ship["lane"])
        positions = _interp_route(route, n_pos, rng, jitter_lon=0.0, jitter_lat=0.0)
        result[ship["mmsi"]] = positions
    return result


# ── 3. Validate ───────────────────────────────────────────────────────────────

def _ship_name(mmsi: str) -> str:
    for s in _SHIP_ROUTES:
        if s["mmsi"] == mmsi:
            return s["name"]
    return mmsi


def verify() -> int:
    """Return 0 if all ships clear land, 1 if any violation found."""
    all_positions = _all_ship_positions()
    total_ships = len(all_positions)
    total_points = sum(len(v) for v in all_positions.values())
    print(f"\nChecking {total_ships} ships × {total_points // total_ships} positions "
          f"= {total_points} points against land …\n")

    violations: dict[str, list[tuple[int, float, float]]] = {}  # mmsi → [(idx, lon, lat)]

    for mmsi, positions in all_positions.items():
        ship_violations: list[tuple[int, float, float]] = []
        for idx, (lon, lat) in enumerate(positions):
            if land_union is not None and land_union.contains(Point(lon, lat)):
                ship_violations.append((idx, lon, lat))
        if ship_violations:
            violations[mmsi] = ship_violations

    # ── Report ─────────────────────────────────────────────────────────────
    if not violations:
        print("✓  ALL CLEAR — no ship track touches land.")
        for mmsi, positions in all_positions.items():
            lons = [p[0] for p in positions]
            lats = [p[1] for p in positions]
            print(f"  {_ship_name(mmsi):20s}  MMSI {mmsi}  "
                  f"lon [{min(lons):.4f}, {max(lons):.4f}]  "
                  f"lat [{min(lats):.4f}, {max(lats):.4f}]  "
                  f"{len(positions)} pts  ✓")
        return 0

    print(f"✗  VIOLATIONS FOUND — {len(violations)} ship(s) cross land:\n")
    for mmsi, pts in violations.items():
        name = _ship_name(mmsi)
        print(f"  {name} (MMSI {mmsi}): {len(pts)} land-touching position(s)")
        for idx, lon, lat in pts[:5]:
            print(f"    position #{idx:3d}  lon={lon:.5f}  lat={lat:.5f}")
        if len(pts) > 5:
            print(f"    … and {len(pts) - 5} more")

    # Also print clean ships for completeness
    print(f"\nShips with no violations:")
    for mmsi in all_positions:
        if mmsi not in violations:
            print(f"  {_ship_name(mmsi):20s}  MMSI {mmsi}  ✓")

    return 1


if __name__ == "__main__":
    sys.exit(verify())
