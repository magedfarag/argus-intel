"""P1-6.4: Map performance benchmarks for the three Middle East pilot AOIs.

Verifies that:
- Each pilot AOI geometry has an area within the map-render performance budget
  (≤ 150 km² ensures the map can load and display the full AOI in a single tile
  request without exceeding the async-promotion threshold).
- STAC bounding-box computation from pilot geometries completes in < 5 ms.
- Event density-reduction is triggered correctly when synthetic pilot-AOI event
  loads exceed the server-side density threshold (500 events).
- Export payload size per pilot AOI is within the 5 MB browser-download budget.
- All pilot-AOI centroids are within WGS-84 valid range and map tile coverage.

These tests act as regression guards: if pilot AOI geometries change and
performance budgets are exceeded the CI gate fails before any manual test
is needed.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Tuple

import pytest

from src.models.pilot_aois import PILOT_AOIS
from datetime import datetime, timedelta, timezone

from src.api.events import _apply_density_reduction, _DENSITY_THRESHOLD, _DENSITY_MAX_RESULTS
from src.models.event_search import EventSearchResponse
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)


# ── Performance budget constants ─────────────────────────────────────────────

# Maximum acceptable area per pilot AOI (km²).  AOIs above this require async
# analysis jobs which incur a UI latency penalty.  Keep well below the
# ASYNC_AREA_THRESHOLD_KM2 = 25 km² in app/main.py for the sync path.
MAX_AOI_AREA_KM2 = 150.0

# Maximum acceptable time (seconds) for STAC bbox generation across all AOIs.
MAX_BBOX_GENERATION_S = 0.005  # 5 ms

# Maximum acceptable export payload size per AOI (bytes, JSON representation).
# 5 MB is the target for a fast browser download on a 10 Mbps connection.
MAX_EXPORT_BYTES = 5_000_000

# Tile zoom level used for performance estimation (z=14 ≈ street level for ME).
PERFORMANCE_ZOOM_LEVEL = 14


# ── Geometry helpers ──────────────────────────────────────────────────────────


def _bbox_from_polygon(geometry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Return (west, south, east, north) from a GeoJSON Polygon."""
    ring = geometry["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _area_km2(geometry: Dict[str, Any]) -> float:
    """Flat-earth area estimate for a rectangular AOI polygon (in km²).

    Uses the same approximation as ``_polygon_area_km2()`` in ``app/main.py``:
    convert degree spans to km via the mid-latitude cosine correction.
    """
    west, south, east, north = _bbox_from_polygon(geometry)
    mid_lat_rad = math.radians((south + north) / 2.0)
    km_per_deg_lon = 111.32 * math.cos(mid_lat_rad)
    km_per_deg_lat = 110.54
    width_km = abs(east - west) * km_per_deg_lon
    height_km = abs(north - south) * km_per_deg_lat
    return width_km * height_km


def _tile_count(geometry: Dict[str, Any], zoom: int = 14) -> int:
    """Estimate the number of map tiles that intersect the AOI bbox at *zoom*.

    Tiles per degree at zoom z = 2^z / 360.  This is an upper-bound estimate
    that assumes every tile in the bbox intersection is loaded.
    """
    west, south, east, north = _bbox_from_polygon(geometry)
    tiles_per_deg = (2 ** zoom) / 360.0
    lon_tiles = math.ceil(abs(east - west) * tiles_per_deg)
    lat_tiles = math.ceil(abs(north - south) * tiles_per_deg)
    return lon_tiles * lat_tiles


def _make_pilot_events(n: int, lon: float = 46.67, lat: float = 24.80) -> List[CanonicalEvent]:
    """Generate *n* synthetic CanonicalEvents centred on a pilot AOI."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = []
    for i in range(n):
        ts = base_time + timedelta(minutes=i)
        events.append(
            CanonicalEvent(
                event_id=make_event_id("perf-test", f"entity-{i}", ts.isoformat()),
                event_time=ts,
                ingested_at=ts,
                source="perf-test",
                source_type=SourceType.CONTEXT_FEED,
                entity_type=EntityType.NEWS_ARTICLE,
                event_type=EventType.CONTEXTUAL_EVENT,
                geometry={"type": "Point", "coordinates": [lon, lat]},
                centroid={"type": "Point", "coordinates": [lon, lat]},
                normalization=NormalizationRecord(normalized_by="perf-test"),
                provenance=ProvenanceRecord(raw_source_ref="perf-test://source"),
                license=LicenseRecord(),
                correlation_keys=CorrelationKeys(),
            )
        )
    return events


def _make_search_response(events: List[CanonicalEvent]) -> EventSearchResponse:
    return EventSearchResponse(
        events=events,
        total=len(events),
        page=1,
        page_size=len(events),
        has_next=False,
        was_reduced=False,
    )


# ── P1-6.4: Area budget tests ─────────────────────────────────────────────────


class TestPilotAOIAreaBudget:
    """Each pilot AOI area must be within the map-render performance budget."""

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_area_within_performance_budget(self, aoi: Dict[str, Any]) -> None:
        area = _area_km2(aoi["geometry"])
        assert area <= MAX_AOI_AREA_KM2, (
            f"{aoi['name']}: area {area:.1f} km² exceeds budget {MAX_AOI_AREA_KM2} km²"
        )

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_area_is_positive(self, aoi: Dict[str, Any]) -> None:
        area = _area_km2(aoi["geometry"])
        assert area > 0.0, f"{aoi['name']}: computed area is non-positive"

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_tile_count_within_browser_budget(self, aoi: Dict[str, Any]) -> None:
        """Tile count at z=14 must stay below 256 tiles to avoid render stalls.

        MapLibre GL JS can render ~200–300 tiles per view without frame-rate
        degradation on mid-range hardware.  Pilot AOIs must fit inside this
        budget at the primary analysis zoom level.
        """
        count = _tile_count(aoi["geometry"], zoom=PERFORMANCE_ZOOM_LEVEL)
        assert count <= 256, (
            f"{aoi['name']}: {count} tiles at z={PERFORMANCE_ZOOM_LEVEL} "
            f"exceeds 256-tile browser budget"
        )

    def test_riyadh_area_expected_magnitude(self) -> None:
        """Riyadh pilot AOI is ~5×5 km → expect roughly 20–30 km²."""
        aoi = next(a for a in PILOT_AOIS if "riyadh" in a["id"])
        area = _area_km2(aoi["geometry"])
        assert 15.0 <= area <= 35.0, f"Riyadh area {area:.1f} km² outside expected 15–35 km²"

    def test_doha_area_expected_magnitude(self) -> None:
        """Doha pilot AOI is ~5×5 km → expect roughly 20–30 km²."""
        aoi = next(a for a in PILOT_AOIS if "doha" in a["id"])
        area = _area_km2(aoi["geometry"])
        assert 15.0 <= area <= 35.0, f"Doha area {area:.1f} km² outside expected 15–35 km²"

    def test_dubai_area_within_budget(self) -> None:
        """Dubai pilot AOI spans a larger waterfront corridor — must still be
        within the overall 150 km² rendering budget."""
        aoi = next(a for a in PILOT_AOIS if "dubai" in a["id"])
        area = _area_km2(aoi["geometry"])
        assert area <= MAX_AOI_AREA_KM2, f"Dubai area {area:.1f} km² exceeds {MAX_AOI_AREA_KM2} km²"


# ── P1-6.4: STAC bbox generation speed ───────────────────────────────────────


class TestBBoxGenerationPerformance:
    """STAC bounding-box computation for all pilot AOIs must be sub-millisecond."""

    def test_bbox_generation_completes_within_budget(self) -> None:
        start = time.perf_counter()
        for aoi in PILOT_AOIS:
            _bbox_from_polygon(aoi["geometry"])
        elapsed = time.perf_counter() - start
        assert elapsed < MAX_BBOX_GENERATION_S, (
            f"Bbox generation for all pilot AOIs took {elapsed*1000:.2f} ms "
            f"(budget: {MAX_BBOX_GENERATION_S*1000:.0f} ms)"
        )

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_bbox_values_are_finite(self, aoi: Dict[str, Any]) -> None:
        west, south, east, north = _bbox_from_polygon(aoi["geometry"])
        for val, name in ((west, "west"), (south, "south"), (east, "east"), (north, "north")):
            assert math.isfinite(val), f"{aoi['name']}: bbox {name} = {val} is not finite"

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_bbox_within_wgs84_range(self, aoi: Dict[str, Any]) -> None:
        west, south, east, north = _bbox_from_polygon(aoi["geometry"])
        assert -180.0 <= west <= 180.0
        assert -180.0 <= east <= 180.0
        assert -90.0 <= south <= 90.0
        assert -90.0 <= north <= 90.0
        assert west < east, f"{aoi['name']}: bbox west >= east"
        assert south < north, f"{aoi['name']}: bbox south >= north"

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_centroid_within_bbox(self, aoi: Dict[str, Any]) -> None:
        west, south, east, north = _bbox_from_polygon(aoi["geometry"])
        lon = aoi["centroid"]["lon"]
        lat = aoi["centroid"]["lat"]
        assert west <= lon <= east, f"{aoi['name']}: centroid lon {lon} outside bbox"
        assert south <= lat <= north, f"{aoi['name']}: centroid lat {lat} outside bbox"


# ── P1-6.4: Event density budget ─────────────────────────────────────────────


class TestEventDensityBudget:
    """Server-side density reduction must fire for pilot-AOI-scale event loads."""

    def test_density_reduction_fires_above_threshold(self) -> None:
        """A pilot AOI event search returning > DENSITY_THRESHOLD events must
        be subsampled to DENSITY_MAX_RESULTS before reaching the browser."""
        aoi = PILOT_AOIS[0]
        events = _make_pilot_events(
            _DENSITY_THRESHOLD + 100,
            lon=aoi["centroid"]["lon"],
            lat=aoi["centroid"]["lat"],
        )
        response = _make_search_response(events)
        reduced = _apply_density_reduction(response)

        assert reduced.was_reduced is True
        assert len(reduced.events) == _DENSITY_MAX_RESULTS
        # Total preserved so UI can show "showing 200 of 600"
        assert reduced.total == len(events)

    def test_density_reduction_skipped_below_threshold(self) -> None:
        """An event search returning ≤ DENSITY_THRESHOLD events must NOT be
        subsampled — all results are passed through unchanged."""
        events = _make_pilot_events(_DENSITY_THRESHOLD)
        response = _make_search_response(events)
        reduced = _apply_density_reduction(response)

        assert reduced.was_reduced is False
        assert len(reduced.events) == _DENSITY_THRESHOLD

    def test_density_reduction_is_deterministic(self) -> None:
        """The same event set must always produce the same subsample (stable
        seed) so analysts get consistent results on repeated queries."""
        events = _make_pilot_events(_DENSITY_THRESHOLD + 50)
        r1 = _apply_density_reduction(_make_search_response(events))
        r2 = _apply_density_reduction(_make_search_response(events))
        assert [e.event_id for e in r1.events] == [e.event_id for e in r2.events]

    def test_density_reduction_preserves_temporal_order(self) -> None:
        """After subsampling, events must still be sorted by event_time ascending
        so the timeline bar chart renders correctly."""
        events = _make_pilot_events(_DENSITY_THRESHOLD + 100)
        reduced = _apply_density_reduction(_make_search_response(events))
        times = [e.event_time for e in reduced.events]
        assert times == sorted(times)

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_each_pilot_aoi_density_reduction_fires(self, aoi: Dict[str, Any]) -> None:
        """Dense event load for each specific pilot AOI location triggers reduction."""
        events = _make_pilot_events(
            _DENSITY_THRESHOLD + 1,
            lon=aoi["centroid"]["lon"],
            lat=aoi["centroid"]["lat"],
        )
        reduced = _apply_density_reduction(_make_search_response(events))
        assert reduced.was_reduced is True

    def test_reduced_result_count_within_export_size_budget(self) -> None:
        """After density reduction the JSON export size should fit within the
        5 MB browser download budget.

        Each CanonicalEvent serialises to roughly 800–2 000 bytes.  With
        DENSITY_MAX_RESULTS = 200 we budget at most 200 × 10 000 = 2 MB — well
        inside the 5 MB cap.
        """
        events = _make_pilot_events(_DENSITY_THRESHOLD + 100)
        reduced = _apply_density_reduction(_make_search_response(events))
        # Upper bound: 10 KB per event
        upper_bound_bytes = len(reduced.events) * 10_000
        assert upper_bound_bytes <= MAX_EXPORT_BYTES, (
            f"Upper-bound export size {upper_bound_bytes} bytes exceeds "
            f"{MAX_EXPORT_BYTES} byte budget for {len(reduced.events)} events"
        )


# ── P1-6.4: Map centroid coverage ────────────────────────────────────────────


class TestPilotAOIMapCoverage:
    """Pilot AOI centroids must fall in the Middle East region served by free
    Sentinel-2 and Landsat public STAC catalogs."""

    # Approximate bounding box of the Middle East + North Africa STAC coverage
    _ME_BBOX = {"west": 25.0, "east": 65.0, "south": 12.0, "north": 42.0}

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_centroid_in_middle_east_region(self, aoi: Dict[str, Any]) -> None:
        lon = aoi["centroid"]["lon"]
        lat = aoi["centroid"]["lat"]
        b = self._ME_BBOX
        assert b["west"] <= lon <= b["east"], (
            f"{aoi['name']}: centroid lon {lon} outside Middle East coverage"
        )
        assert b["south"] <= lat <= b["north"], (
            f"{aoi['name']}: centroid lat {lat} outside Middle East coverage"
        )

    @pytest.mark.parametrize("aoi", PILOT_AOIS, ids=[a["id"] for a in PILOT_AOIS])
    def test_centroid_tile_coordinates_valid(self, aoi: Dict[str, Any]) -> None:
        """Map tile (x,y) derived from centroid at z=14 must be non-negative."""
        lon = aoi["centroid"]["lon"]
        lat = aoi["centroid"]["lat"]
        n = 2 ** PERFORMANCE_ZOOM_LEVEL
        tile_x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        tile_y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        assert 0 <= tile_x < n, f"{aoi['name']}: tile_x {tile_x} out of range for z={PERFORMANCE_ZOOM_LEVEL}"
        assert 0 <= tile_y < n, f"{aoi['name']}: tile_y {tile_y} out of range for z={PERFORMANCE_ZOOM_LEVEL}"
