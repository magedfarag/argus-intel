from __future__ import annotations

from collections import defaultdict
from math import isclose
import random

from shapely.geometry import Point, Polygon

from src.services import demo_seeder

_MUSANDAM_LANDMASS = Polygon([
    (56.18, 25.70),
    (56.28, 25.88),
    (56.38, 26.06),
    (56.50, 26.20),
    (56.66, 26.26),
    (56.74, 26.18),
    (56.72, 25.96),
    (56.60, 25.76),
    (56.42, 25.64),
    (56.24, 25.64),
])


def _coords(feature) -> tuple[float, float]:
    geom = feature.geometry
    coords = geom["coordinates"]
    if geom["type"] == "Point":
        lon, lat = coords
        return float(lon), float(lat)
    # Polygon centroid is stored separately for imagery events.
    lon, lat = feature.centroid["coordinates"]
    return float(lon), float(lat)


def _assert_lane_bounds(lon: float, lat: float, lane: str) -> None:
    if lane == "north_inbound":
        if demo_seeder._CRITICAL_STRAIT_LON_MIN <= lon <= demo_seeder._CRITICAL_STRAIT_LON_MAX:
            assert lat >= demo_seeder._NORTHBOUND_MIN_LAT
    elif lane == "south_outbound":
        if demo_seeder._CRITICAL_STRAIT_LON_MIN <= lon <= demo_seeder._CRITICAL_STRAIT_LON_MAX:
            assert lat <= demo_seeder._SOUTHBOUND_MAX_LAT
        if 56.18 <= lon <= 56.45:
            assert lat <= demo_seeder._SOUTHBOUND_MUSANDAM_MAX_LAT
    elif lane == "oman_coastal":
        if lon >= 56.20:
            assert lat <= demo_seeder._OMAN_COAST_MAX_LAT
    elif lane == "musandam_rounding":
        if demo_seeder._CRITICAL_STRAIT_LON_MIN <= lon <= demo_seeder._CRITICAL_STRAIT_LON_MAX:
            assert lat <= demo_seeder._MUSANDAM_ROUNDING_MAX_LAT
    else:
        raise AssertionError(f"Unknown ship lane: {lane}")


def test_ship_events_stay_at_surface_level() -> None:
    events = demo_seeder._ship_events()
    assert events

    for event in events:
        assert event.entity_type.value == "vessel"
        assert event.event_type.value == "ship_position"
        assert event.altitude_m == 0
        assert event.attributes["route_lane"] in {
            "north_inbound",
            "south_outbound",
            "oman_coastal",
            "musandam_rounding",
        }


def test_ship_routes_remain_in_plausible_hormuz_lanes() -> None:
    for ship in demo_seeder._SHIP_ROUTES:
        route = demo_seeder._deterministic_lane_route(ship["mmsi"], ship["lane"])
        samples = demo_seeder._interp_route(route, 120, random.Random(0), jitter_lon=0.0, jitter_lat=0.0)
        for lon, lat in samples:
            assert demo_seeder._LON_MIN <= lon <= demo_seeder._LON_MAX
            assert demo_seeder._LAT_MIN <= lat <= demo_seeder._LAT_MAX
            _assert_lane_bounds(lon, lat, ship["lane"])
            if ship["lane"] == "north_inbound":
                assert not _MUSANDAM_LANDMASS.contains(Point(lon, lat)), (
                    f"{ship['name']} cuts across the Musandam peninsula at {(lon, lat)!r}"
                )


def test_problematic_demo_mmsis_stay_offshore_across_full_timeline() -> None:
    events = demo_seeder._ship_events()
    assert events

    by_mmsi: dict[str, list[tuple[float, float]]] = {
        "215631000": [],
        "538006712": [],
        "636021800": [],
    }

    for event in events:
        mmsi = str(event.attributes.get("mmsi", ""))
        if mmsi in by_mmsi:
            lon, lat = _coords(event)
            by_mmsi[mmsi].append((lon, lat))

    for mmsi, coords in by_mmsi.items():
        assert coords, f"No generated points found for MMSI {mmsi}"

    # GULF BREEZE (Oman coastal lane): should stay south and offshore.
    gulf_breeze = by_mmsi["215631000"]
    assert min(lat for _, lat in gulf_breeze) >= 25.50
    assert max(lat for _, lat in gulf_breeze) <= 25.62

    # ORIENT PEARL (southbound lane): should not climb into the northbound corridor.
    orient_pearl = by_mmsi["538006712"]
    assert min(lat for _, lat in orient_pearl) >= 25.50
    assert max(lat for _, lat in orient_pearl) <= 25.62

    # MUSANDAM LINK (rounding lane): must round the cape without crossing inland.
    musandam_link = by_mmsi["636021800"]
    assert min(lat for _, lat in musandam_link) >= 25.50
    assert max(lat for _, lat in musandam_link) <= 25.62


def test_aircraft_events_have_positive_altitude_from_source_data() -> None:
    events = demo_seeder._aircraft_events()
    assert events

    altitudes = defaultdict(list)
    for event in events:
        assert event.entity_type.value == "aircraft"
        assert event.event_type.value == "aircraft_position"
        assert event.altitude_m is not None
        assert event.altitude_m >= 4500
        assert event.attributes["on_ground"] is False
        assert event.attributes["baro_altitude_m"] > 0
        assert event.attributes["geo_altitude_m"] > 0
        altitudes[event.entity_id].append(event.altitude_m)

    assert all(len(values) >= 2 for values in altitudes.values())
    assert any(max(values) != min(values) for values in altitudes.values())


def test_contextual_events_are_anchored_to_curated_locations() -> None:
    gdelt = demo_seeder._gdelt_events()
    assert len(gdelt) == len(demo_seeder._GDELT_HEADLINES)

    expected = {
        headline: (lon, lat, publication, location_name)
        for headline, _themes, lon, lat, publication, location_name in demo_seeder._GDELT_HEADLINES
    }

    for event in gdelt:
        headline = event.attributes["headline"]
        lon, lat = _coords(event)
        exp_lon, exp_lat, exp_pub, exp_location = expected[headline]
        assert isclose(lon, exp_lon, abs_tol=1e-6)
        assert isclose(lat, exp_lat, abs_tol=1e-6)
        assert event.attributes["source_publication"] == exp_pub
        assert event.attributes["location_name"] == exp_location
        assert event.event_type.value == "contextual_event"

    ops = demo_seeder._operational_events()
    expected_ops = {
        "DXB-PORT-2026-1184": (55.18, 25.27),
        "OMN-PSC-2026-041": (56.11, 26.04),
        "IRN-INFRA-2026-228": (56.92, 26.78),
        "MSI-CASE-2026-092": (55.74, 25.94),
        "MCT-FLT-2026-077": (57.06, 25.19),
        "UAE-CST-2026-309": (55.46, 26.62),
        "FJR-ENG-2026-188": (56.44, 25.69),
        "HRMZ-OPS-2026-204": (56.52, 26.56),
        "IRN-SHP-2026-144": (55.94, 26.84),
        "QSM-RNG-2026-011": (56.78, 26.42),
        "ADH-MRN-2026-064": (55.08, 26.96),
        "MUS-AIR-2026-055": (57.22, 25.44),
    }

    for event in ops:
        lon, lat = _coords(event)
        exp_lon, exp_lat = expected_ops[event.attributes["permit_number"]]
        assert isclose(lon, exp_lon, abs_tol=1e-6)
        assert isclose(lat, exp_lat, abs_tol=1e-6)


def test_imagery_events_use_curated_anchor_centroids() -> None:
    events = demo_seeder._imagery_events()
    centroids = {_coords(event) for event in events}

    expected = {
        (cx, cy)
        for _platform, _source, _collection, cx, cy, _hw, _hh, _label in demo_seeder._IMAGERY_SCENES
    }

    assert centroids == expected
