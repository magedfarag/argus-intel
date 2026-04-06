"""Seed the in-memory EventStore with realistic synthetic data for the demo.

Generates ship tracks, flight tracks, GDELT contextual events, and imagery
acquisition events in the Strait of Hormuz area so the UI has data to render
immediately on startup.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import UTC, datetime, timedelta

from src.models.aoi import AOICreate, GeometryModel
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
)
from src.services.aoi_store import AOIStore
from src.services.event_store import EventStore

# AOI: Strait of Hormuz bounding box
_LON_MIN, _LON_MAX = 54.83, 57.44
_LAT_MIN, _LAT_MAX = 24.99, 27.32
_AOI_ID = "5bc84ca9-a46b-47e9-a735-8fd000fd3123"

_NORM = NormalizationRecord(normalized_by="demo-seeder")
_PROV = ProvenanceRecord(raw_source_ref="demo://seeder")
_LIC = LicenseRecord()
_NOW = datetime.now(UTC)


def _eid(prefix: str, *parts: str) -> str:
    h = hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]
    return f"{prefix}-{h}"


def _point(lon: float, lat: float) -> dict:
    return {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}


def _rect_polygon(cx: float, cy: float, half_width: float, half_height: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [round(cx - half_width, 5), round(cy - half_height, 5)],
            [round(cx + half_width, 5), round(cy - half_height, 5)],
            [round(cx + half_width, 5), round(cy + half_height, 5)],
            [round(cx - half_width, 5), round(cy + half_height, 5)],
            [round(cx - half_width, 5), round(cy - half_height, 5)],
        ]],
    }


def _validate_point_in_aoi(label: str, lon: float, lat: float) -> None:
    if not (_LON_MIN <= lon <= _LON_MAX and _LAT_MIN <= lat <= _LAT_MAX):
        raise ValueError(f"{label} lies outside the demo AOI at {(lon, lat)!r}")


# ── Demo geography anchors ───────────────────────────────────────────────────

_CRITICAL_STRAIT_LON_MIN = 56.05
_CRITICAL_STRAIT_LON_MAX = 56.78
_NORTHBOUND_MIN_LAT = 26.44
_SOUTHBOUND_MAX_LAT = 26.10
_SOUTHBOUND_MUSANDAM_MAX_LAT = 25.62
_SOUTHBOUND_MIN_LAT = 25.50
_OMAN_COAST_MAX_LAT = 25.62
_OMAN_COAST_MIN_LAT = 25.50
_MUSANDAM_ROUNDING_MAX_LAT = 26.22
_NORTHBOUND_EASTERN_MAX_LAT = 26.58
_AIRCRAFT_MIN_ALTITUDE_M = 4500.0

_NORTHBOUND_TEMPLATE: list[tuple[float, float]] = [
    (57.30, 26.52),
    (57.02, 26.53),
    (56.74, 26.54),
    (56.40, 26.56),
    (56.00, 26.56),
    (55.58, 26.52),
]

_SOUTHBOUND_TEMPLATE: list[tuple[float, float]] = [
    (55.12, 25.56),
    (55.46, 25.57),
    (55.86, 25.58),
    (56.26, 25.56),
    (56.66, 25.54),
    (57.16, 25.52),
]

_OMAN_COASTAL_TEMPLATE: list[tuple[float, float]] = [
    (57.24, 25.58),
    (56.98, 25.59),
    (56.72, 25.60),
    (56.46, 25.60),
    (56.22, 25.60),
]


def _deterministic_lane_route(mmsi: str, lane: str) -> list[tuple[float, float]]:
    """Build a water-safe route from lane templates with tiny deterministic offsets."""
    offset_seed = int(mmsi[-2:])
    lon_offset = ((offset_seed % 5) - 2) * 0.01
    lat_offset = (((offset_seed // 5) % 5) - 2) * 0.005

    if lane == "north_inbound":
        template = _NORTHBOUND_TEMPLATE
        min_lat = _NORTHBOUND_MIN_LAT
        max_lat = _NORTHBOUND_EASTERN_MAX_LAT
    elif lane == "south_outbound":
        template = _SOUTHBOUND_TEMPLATE
        min_lat = _SOUTHBOUND_MIN_LAT
        max_lat = _SOUTHBOUND_MUSANDAM_MAX_LAT
    elif lane in {"oman_coastal", "musandam_rounding"}:
        template = _OMAN_COASTAL_TEMPLATE
        min_lat = _OMAN_COAST_MIN_LAT
        max_lat = _OMAN_COAST_MAX_LAT
    else:
        raise ValueError(f"Unknown ship lane {lane!r} for route generation")

    route: list[tuple[float, float]] = []
    for lon, lat in template:
        route.append((
            min(max(lon + lon_offset, _LON_MIN + 0.02), _LON_MAX - 0.02),
            min(max(lat + lat_offset, min_lat), max_lat),
        ))
    return route


# ── Ship tracks ──────────────────────────────────────────────────────────────
# Demo vessel tracks stay in clearly navigable water inside the Strait of
# Hormuz traffic lanes or along the Gulf of Oman coast. We keep them away from
# the Musandam landmass by construction and then validate the interpolated
# points again before emitting seed events.

_SHIP_ROUTES = [
    {
        "mmsi": "211330000",
        "name": "EVER GRACE",
        "ship_type": 70,
        "dest": "Bandar Abbas",
        "lane": "north_inbound",
        "speed_kn": 13.5,
        "route": [
            (57.18, 25.70),
            (57.00, 25.96),
            (56.90, 26.10),  # Stay south until clear of Musandam
            (56.82, 26.30),  # Deep in critical strait, approaching north transit
            (56.78, 26.44),  # Just at the boundary, not over Musandam
            (56.68, 26.56),
            (56.50, 26.58),
            (56.34, 26.60),
            (56.18, 26.58),
            (56.04, 26.56),
        ],
    },
    {
        "mmsi": "636017432",
        "name": "STELLA MARINER",
        "ship_type": 70,
        "dest": "Jebel Ali",
        "lane": "north_inbound",
        "speed_kn": 12.0,
        "route": [
            (57.28, 25.62),
            (57.06, 25.88),
            (56.92, 26.10),  # Safe transition point south
            (56.84, 26.30),  # Deep in critical strait
            (56.78, 26.44),  # North of Musandam
            (56.68, 26.54),
            (56.44, 26.58),
            (56.16, 26.58),
            (55.82, 26.56),
            (55.42, 26.52),
        ],
    },
    {
        "mmsi": "352456000",
        "name": "HORMUZ CARRIER",
        "ship_type": 70,
        "dest": "Khalifa Port",
        "lane": "north_inbound",
        "speed_kn": 11.5,
        "route": [
            (57.10, 25.86),
            (56.98, 26.00),  # Safe approach
            (56.88, 26.18),  # Final approach
            (56.78, 26.44),  # North of Musandam
            (56.70, 26.56),
            (56.56, 26.58),
            (56.28, 26.58),
            (55.94, 26.56),
            (55.54, 26.52),
        ],
    },
    {
        "mmsi": "477123400",
        "name": "PACIFIC VOYAGER",
        "ship_type": 80,
        "dest": "Fujairah",
        "lane": "south_outbound",
        "speed_kn": 14.0,
        "route": [
            (55.14, 26.58),
            (55.46, 26.34),
            (55.78, 26.06),
            (55.98, 25.72),
            (56.18, 25.54),
            (56.44, 25.46),
            (56.78, 25.38),
            (57.16, 25.30),
        ],
    },
    {
        "mmsi": "538006712",
        "name": "ORIENT PEARL",
        "ship_type": 80,
        "dest": "Muscat",
        "lane": "south_outbound",
        "speed_kn": 12.5,
        "route": [
            (55.04, 26.48),
            (55.30, 26.28),
            (55.60, 26.02),
            (55.86, 25.78),
            (56.08, 25.60),
            (56.34, 25.48),
            (56.68, 25.36),
            (57.12, 25.14),
        ],
    },
    {
        "mmsi": "440123456",
        "name": "EASTERN STAR",
        "ship_type": 80,
        "dest": "Indian Ocean",
        "lane": "south_outbound",
        "speed_kn": 10.5,
        "route": [
            (55.18, 26.64),
            (55.50, 26.38),
            (55.78, 26.08),
            (56.00, 25.80),
            (56.24, 25.60),
            (56.50, 25.46),
            (56.84, 25.38),
            (57.22, 25.32),
        ],
    },
    {
        "mmsi": "249987000",
        "name": "CASPIAN PRIDE",
        "ship_type": 70,
        "dest": "Bandar Abbas",
        "lane": "north_inbound",
        "speed_kn": 9.4,
        "route": [
            (57.08, 25.80),
            (56.96, 26.00),  # Safe transition
            (56.84, 26.24),  # Final approach
            (56.78, 26.44),  # North of Musandam
            (56.68, 26.56),
            (56.56, 26.58),
            (56.36, 26.58),
            (56.16, 26.56),
            (55.98, 26.54),
        ],
    },
    {
        "mmsi": "215631000",
        "name": "GULF BREEZE",
        "ship_type": 60,
        "dest": "Khor Fakkan",
        "lane": "oman_coastal",
        "speed_kn": 8.5,
        "route": [
            (57.24, 25.18),
            (57.08, 25.19),
            (56.92, 25.21),
            (56.76, 25.24),
            (56.60, 25.27),
            (56.44, 25.31),
            (56.28, 25.38),
        ],
    },
    {
        "mmsi": "466001000",
        "name": "AL ZUBARA",
        "ship_type": 80,
        "dest": "Arabian Sea",
        "lane": "south_outbound",
        "speed_kn": 11.0,
        "route": [
            (55.08, 26.54),
            (55.34, 26.28),
            (55.60, 26.02),
            (55.86, 25.74),
            (56.12, 25.56),
            (56.40, 25.44),
            (56.74, 25.34),
            (57.20, 25.14),
        ],
    },
    {
        "mmsi": "422002000",
        "name": "JAHAN HEROES",
        "ship_type": 70,
        "dest": "Bandar Abbas",
        "lane": "north_inbound",
        "speed_kn": 12.5,
        "route": [
            (57.32, 25.56),
            (57.14, 25.76),  # South approach
            (56.98, 26.06),  # Safe transition
            (56.82, 26.30),  # Deep approach
            (56.78, 26.44),  # North of Musandam
            (56.70, 26.54),
            (56.52, 26.58),
            (56.34, 26.58),
            (56.16, 26.56),
            (56.00, 26.54),
        ],
    },
    {
        "mmsi": "371002000",
        "name": "KHOR DUBAI",
        "ship_type": 70,
        "dest": "Jebel Ali",
        "lane": "north_inbound",
        "speed_kn": 13.0,
        "route": [
            (57.24, 25.68),
            (57.06, 25.88),  # South approach
            (56.90, 26.12),  # Safe transition
            (56.82, 26.30),  # Deep in critical strait
            (56.78, 26.44),  # North of Musandam
            (56.68, 26.54),
            (56.40, 26.58),
            (56.08, 26.56),
            (55.72, 26.52),
            (55.30, 26.46),
        ],
    },
    {
        "mmsi": "403110120",
        "name": "SAFAT HORIZON",
        "ship_type": 80,
        "dest": "Duqm",
        "lane": "south_outbound",
        "speed_kn": 11.8,
        "route": [
            (55.20, 26.52),
            (55.52, 26.30),
            (55.80, 26.02),
            (56.02, 25.70),
            (56.24, 25.54),
            (56.48, 25.48),
            (56.82, 25.36),
            (57.24, 25.16),
        ],
    },
    {
        "mmsi": "422119900",
        "name": "PERSIAN VECTOR",
        "ship_type": 80,
        "dest": "Bandar Abbas",
        "lane": "north_inbound",
        "speed_kn": 12.2,
        "route": [
            (57.22, 25.60),
            (57.06, 25.80),  # South approach
            (56.92, 26.04),  # Safe transition
            (56.82, 26.28),  # Deep approach
            (56.78, 26.44),  # North of Musandam
            (56.68, 26.56),
            (56.50, 26.58),
            (56.30, 26.58),
            (56.10, 26.56),
            (55.92, 26.54),
        ],
    },
    {
        "mmsi": "248450000",
        "name": "QESHM RUNNER",
        "ship_type": 70,
        "dest": "Bandar Abbas Roads",
        "lane": "north_inbound",
        "speed_kn": 14.4,
        "route": [
            (57.18, 25.74),
            (57.02, 25.90),  # Approach turn
            (56.88, 26.12),  # Safe transition
            (56.80, 26.32),  # Deep approach
            (56.78, 26.44),  # North of Musandam
            (56.68, 26.56),
            (56.52, 26.58),
            (56.34, 26.58),
            (56.16, 26.56),
            (56.00, 26.54),
        ],
    },
    {
        "mmsi": "636021800",
        "name": "MUSANDAM LINK",
        "ship_type": 60,
        "dest": "Khor Fakkan",
        "lane": "musandam_rounding",
        "speed_kn": 15.0,
        "route": [
            (56.08, 25.78),
            (56.30, 25.68),
            (56.56, 25.54),
            (56.80, 25.42),
            (56.98, 25.34),
            (57.10, 25.24),
        ],
    },
]

_ACTIVE_WAR_SCENARIO_SHIPS = {
    "211330000",  # EVER GRACE
    "477123400",  # PACIFIC VOYAGER
    "538006712",  # ORIENT PEARL
    "215631000",  # GULF BREEZE
    "422002000",  # JAHAN HEROES
    "403110120",  # SAFAT HORIZON
    "422119900",  # PERSIAN VECTOR
    "636021800",  # MUSANDAM LINK
}


def _validate_ship_positions(ship_name: str, lane: str, positions: list[tuple[float, float]]) -> None:
    for lon, lat in positions:
        if not (_LON_MIN <= lon <= _LON_MAX and _LAT_MIN <= lat <= _LAT_MAX):
            raise ValueError(f"{ship_name} left the demo AOI at {(lon, lat)!r}")

    if lane == "north_inbound":
        offenders = [
            (lon, lat)
            for lon, lat in positions
            if _CRITICAL_STRAIT_LON_MIN <= lon <= _CRITICAL_STRAIT_LON_MAX and lat < _NORTHBOUND_MIN_LAT
        ]
        eastern_offenders = [
            (lon, lat)
            for lon, lat in positions
            if lon >= 56.70 and lat > _NORTHBOUND_EASTERN_MAX_LAT
        ]
        if offenders:
            raise ValueError(f"{ship_name} crossed south of the northbound TSS lane: {offenders[:3]!r}")
        if eastern_offenders:
            raise ValueError(f"{ship_name} climbed onto Qeshm/shoreline sector: {eastern_offenders[:3]!r}")
        return

    if lane == "south_outbound":
        offenders = [
            (lon, lat)
            for lon, lat in positions
            if _CRITICAL_STRAIT_LON_MIN <= lon <= _CRITICAL_STRAIT_LON_MAX and lat > _SOUTHBOUND_MAX_LAT
        ]
        shoreline_offenders = [
            (lon, lat)
            for lon, lat in positions
            if 56.08 <= lon <= 56.55 and lat > _SOUTHBOUND_MUSANDAM_MAX_LAT
        ]
        low_lat_offenders = [
            (lon, lat)
            for lon, lat in positions
            if lat < _SOUTHBOUND_MIN_LAT
        ]
        if offenders:
            raise ValueError(f"{ship_name} crossed north of the southbound TSS lane: {offenders[:3]!r}")
        if shoreline_offenders:
            raise ValueError(
                f"{ship_name} hugged the Musandam shoreline too closely: {shoreline_offenders[:3]!r}"
            )
        if low_lat_offenders:
            raise ValueError(f"{ship_name} dipped too close to UAE shoreline: {low_lat_offenders[:3]!r}")
        return

    if lane == "oman_coastal":
        offenders = [
            (lon, lat)
            for lon, lat in positions
            if lon >= 56.20 and lat > _OMAN_COAST_MAX_LAT
        ]
        low_lat_offenders = [
            (lon, lat)
            for lon, lat in positions
            if lat < _OMAN_COAST_MIN_LAT
        ]
        if offenders:
            raise ValueError(f"{ship_name} climbed inland along the Gulf of Oman coast: {offenders[:3]!r}")
        if low_lat_offenders:
            raise ValueError(f"{ship_name} drifted too far south toward shoreline: {low_lat_offenders[:3]!r}")
        return

    if lane == "musandam_rounding":
        offenders = [
            (lon, lat)
            for lon, lat in positions
            if _CRITICAL_STRAIT_LON_MIN <= lon <= _CRITICAL_STRAIT_LON_MAX
            and lat > _MUSANDAM_ROUNDING_MAX_LAT
        ]
        low_lat_offenders = [
            (lon, lat)
            for lon, lat in positions
            if lat < _OMAN_COAST_MIN_LAT
        ]
        if offenders:
            raise ValueError(f"{ship_name} cut across the Musandam landmass: {offenders[:3]!r}")
        if low_lat_offenders:
            raise ValueError(f"{ship_name} drifted too close to shoreline: {low_lat_offenders[:3]!r}")
        return

    raise ValueError(f"Unknown ship lane {lane!r} for {ship_name}")


def _interp_route(
    waypoints: list[tuple[float, float]],
    n_points: int,
    rng: random.Random,
    jitter_lon: float = 0.0005,
    jitter_lat: float = 0.0005,
) -> list[tuple[float, float]]:
    """Linearly interpolate n_points along a list of (lon, lat) waypoints."""
    # Build cumulative segment lengths (simple flat-earth approximation)
    segs: list[float] = [0.0]
    for i in range(1, len(waypoints)):
        dx = (waypoints[i][0] - waypoints[i - 1][0]) * math.cos(math.radians(waypoints[i][1]))
        dy = waypoints[i][1] - waypoints[i - 1][1]
        segs.append(segs[-1] + math.hypot(dx, dy))
    total = segs[-1]
    result: list[tuple[float, float]] = []
    for k in range(n_points):
        t = total * k / max(n_points - 1, 1)
        # Find which segment
        seg_idx = 0
        for s in range(1, len(segs)):
            if segs[s] >= t:
                seg_idx = s - 1
                break
        else:
            seg_idx = len(waypoints) - 2
        frac = (t - segs[seg_idx]) / max(segs[seg_idx + 1] - segs[seg_idx], 1e-9)
        lon = waypoints[seg_idx][0] + frac * (waypoints[seg_idx + 1][0] - waypoints[seg_idx][0])
        lat = waypoints[seg_idx][1] + frac * (waypoints[seg_idx + 1][1] - waypoints[seg_idx][1])
        # Small positional noise (stays on-route)
        lon += rng.gauss(0, jitter_lon)
        lat += rng.gauss(0, jitter_lat)
        result.append((lon, lat))
    return result


def _ship_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(42)
    # Keep trajectories visually smooth while reducing browser/GPU load during
    # replay recording. Lower density improves narration sync in demo capture.
    n_pos = 80
    window_h = 30

    for ship in _SHIP_ROUTES:
        if ship["mmsi"] not in _ACTIVE_WAR_SCENARIO_SHIPS:
            continue
        base_time = _NOW - timedelta(hours=window_h)
        route = _deterministic_lane_route(ship["mmsi"], ship["lane"])
        positions = _interp_route(route, n_pos, rng, jitter_lon=0.0, jitter_lat=0.0)
        _validate_ship_positions(ship["name"], ship["lane"], positions)

        # Compute approximate heading (degrees) between consecutive points
        def _hdg(p0: tuple[float, float], p1: tuple[float, float]) -> float:
            return (math.degrees(math.atan2(p1[0] - p0[0], p1[1] - p0[1])) + 360) % 360

        speed_kn: float = ship["speed_kn"]
        for i, (lon, lat) in enumerate(positions):
            dt = base_time + timedelta(minutes=i * (window_h * 60 // n_pos))
            hdg = _hdg(positions[i - 1], positions[i]) if i > 0 else _hdg(positions[0], positions[1])
            eid = _eid("ship", ship["mmsi"], dt.isoformat())
            events.append(CanonicalEvent(
                event_id=eid,
                source="aisstream",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.VESSEL,
                entity_id=ship["mmsi"],
                event_type=EventType.SHIP_POSITION,
                event_time=dt,
                geometry=_point(lon, lat),
                centroid=_point(lon, lat),
                altitude_m=0,
                confidence=0.95,
                attributes={
                    "mmsi": ship["mmsi"],
                    "vessel_name": ship["name"],
                    "ship_type": ship["ship_type"],
                    "speed_kn": round(speed_kn + rng.gauss(0, 0.5), 1),
                    "course_deg": round(hdg + rng.gauss(0, 3), 1) % 360,
                    "heading_deg": round(hdg, 1),
                    "destination": ship["dest"],
                    "nav_status": "under_way_using_engine",
                    "route_lane": ship["lane"],
                },
                normalization=_NORM,
                provenance=_PROV,
                correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID], mmsi=ship["mmsi"]),
                license=_LIC,
            ))
    return events


# ── Flight tracks ────────────────────────────────────────────────────────────

_AIRCRAFT_ROUTES = [
    {
        "icao24": "710112",
        "callsign": "QTR802",
        "country": "Qatar",
        "origin": "Doha",
        "destination": "Muscat",
        "speed_ms": 244.0,
        "route": [
            (55.02, 25.46),
            (55.48, 25.54),
            (56.00, 25.60),
            (56.50, 25.52),
            (56.96, 25.36),
            (57.28, 25.18),
        ],
        "altitudes_m": [8800, 9500, 10300, 10450, 9800, 9000],
    },
    {
        "icao24": "896340",
        "callsign": "UAE567",
        "country": "United Arab Emirates",
        "origin": "Dubai",
        "destination": "Muscat",
        "speed_ms": 232.0,
        "route": [
            (55.04, 25.20),
            (55.44, 25.22),
            (55.94, 25.24),
            (56.42, 25.20),
            (56.88, 25.14),
            (57.24, 25.08),
        ],
        "altitudes_m": [6500, 7800, 9100, 9700, 9200, 7800],
    },
    {
        "icao24": "730003",
        "callsign": "IRA412",
        "country": "Iran",
        "origin": "Bandar Abbas",
        "destination": "Dubai",
        "speed_ms": 238.0,
        "route": [
            (56.92, 27.08),
            (56.74, 26.86),
            (56.54, 26.60),
            (56.24, 26.26),
            (55.88, 25.92),
            (55.46, 25.58),
            (55.06, 25.28),
        ],
        "altitudes_m": [6900, 7900, 9000, 9700, 9200, 8200, 7100],
    },
    {
        "icao24": "7107a2",
        "callsign": "GFA215",
        "country": "Bahrain",
        "origin": "Bahrain",
        "destination": "Muscat",
        "speed_ms": 252.0,
        "route": [
            (55.00, 25.84),
            (55.44, 25.88),
            (55.94, 25.92),
            (56.42, 25.88),
            (56.88, 25.78),
            (57.22, 25.62),
        ],
        "altitudes_m": [9300, 9900, 10500, 10900, 10300, 9500],
    },
    {
        "icao24": "71be12",
        "callsign": "OMA643",
        "country": "Oman",
        "origin": "Muscat",
        "destination": "Bandar Abbas",
        "speed_ms": 229.0,
        "route": [
            (57.28, 25.20),
            (56.98, 25.44),
            (56.72, 25.74),
            (56.52, 26.06),
            (56.38, 26.40),
            (56.28, 26.78),
        ],
        "altitudes_m": [7200, 8300, 9500, 10200, 9400, 7600],
    },
    {
        "icao24": "710501",
        "callsign": "QTR916",
        "country": "Qatar",
        "origin": "Doha",
        "destination": "Bandar Abbas",
        "speed_ms": 247.0,
        "route": [
            (55.04, 25.96),
            (55.44, 26.02),
            (55.92, 26.12),
            (56.38, 26.28),
            (56.78, 26.52),
            (57.10, 26.82),
        ],
        "altitudes_m": [8600, 9300, 10100, 10600, 10050, 9100],
    },
    {
        "icao24": "4840aa",
        "callsign": "KAC331",
        "country": "Kuwait",
        "origin": "Kuwait City",
        "destination": "Muscat",
        "speed_ms": 257.0,
        "route": [
            (55.00, 26.26),
            (55.44, 26.20),
            (55.94, 26.06),
            (56.42, 25.82),
            (56.88, 25.52),
            (57.22, 25.24),
        ],
        "altitudes_m": [9800, 10300, 10850, 11100, 10550, 9800],
    },
    {
        "icao24": "8965ff",
        "callsign": "ETD441",
        "country": "United Arab Emirates",
        "origin": "Abu Dhabi",
        "destination": "Bandar Abbas",
        "speed_ms": 236.0,
        "route": [
            (55.02, 25.54),
            (55.48, 25.76),
            (55.96, 26.00),
            (56.42, 26.28),
            (56.82, 26.56),
            (57.10, 26.86),
        ],
        "altitudes_m": [7100, 8400, 9700, 10400, 9600, 7900],
    },
    {
        "icao24": "73028c",
        "callsign": "IRA118",
        "country": "Iran",
        "origin": "Shiraz",
        "destination": "Muscat",
        "speed_ms": 245.0,
        "route": [
            (57.06, 27.04),
            (56.90, 26.74),
            (56.68, 26.38),
            (56.42, 26.00),
            (56.10, 25.62),
            (55.72, 25.26),
        ],
        "altitudes_m": [9900, 10300, 10900, 10600, 9600, 8500],
    },
    {
        "icao24": "7060b1",
        "callsign": "KNE204",
        "country": "Saudi Arabia",
        "origin": "Riyadh",
        "destination": "Muscat",
        "speed_ms": 261.0,
        "route": [
            (55.00, 25.34),
            (55.44, 25.40),
            (55.96, 25.46),
            (56.48, 25.42),
            (56.98, 25.30),
            (57.30, 25.14),
        ],
        "altitudes_m": [9300, 9950, 10600, 11100, 10800, 10100],
    },
]

_ACTIVE_WAR_SCENARIO_AIRCRAFT = {
    "710112",  # QTR802
    "896340",  # UAE567
    "730003",  # IRA412
    "71be12",  # OMA643
    "8965ff",  # ETD441
    "7060b1",  # KNE204
}


def _interp_route_with_altitude(
    waypoints: list[tuple[float, float]],
    altitude_profile_m: list[float],
    n_points: int,
    rng: random.Random,
    jitter_lon: float = 0.0012,
    jitter_lat: float = 0.0012,
    jitter_alt_m: float = 45.0,
) -> list[tuple[float, float, float]]:
    if len(waypoints) != len(altitude_profile_m):
        raise ValueError("Aircraft route and altitude profile lengths must match")

    segs: list[float] = [0.0]
    for i in range(1, len(waypoints)):
        dx = (waypoints[i][0] - waypoints[i - 1][0]) * math.cos(math.radians(waypoints[i][1]))
        dy = waypoints[i][1] - waypoints[i - 1][1]
        segs.append(segs[-1] + math.hypot(dx, dy))

    total = segs[-1]
    result: list[tuple[float, float, float]] = []
    for k in range(n_points):
        t = total * k / max(n_points - 1, 1)
        seg_idx = 0
        for s in range(1, len(segs)):
            if segs[s] >= t:
                seg_idx = s - 1
                break
        else:
            seg_idx = len(waypoints) - 2

        frac = (t - segs[seg_idx]) / max(segs[seg_idx + 1] - segs[seg_idx], 1e-9)
        lon = waypoints[seg_idx][0] + frac * (waypoints[seg_idx + 1][0] - waypoints[seg_idx][0])
        lat = waypoints[seg_idx][1] + frac * (waypoints[seg_idx + 1][1] - waypoints[seg_idx][1])
        alt = altitude_profile_m[seg_idx] + frac * (
            altitude_profile_m[seg_idx + 1] - altitude_profile_m[seg_idx]
        )

        lon += rng.gauss(0, jitter_lon)
        lat += rng.gauss(0, jitter_lat)
        alt = max(alt + rng.gauss(0, jitter_alt_m), _AIRCRAFT_MIN_ALTITUDE_M)
        result.append((lon, lat, alt))

    return result


def _validate_aircraft_positions(callsign: str, positions: list[tuple[float, float, float]]) -> None:
    for lon, lat, alt in positions:
        if not (_LON_MIN <= lon <= _LON_MAX and _LAT_MIN <= lat <= _LAT_MAX):
            raise ValueError(f"{callsign} left the demo AOI at {(lon, lat)!r}")
        if alt < _AIRCRAFT_MIN_ALTITUDE_M:
            raise ValueError(f"{callsign} dropped below demo minimum altitude at {alt!r} m")


def _aircraft_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(99)
    n_pos = 60

    for idx, ac in enumerate(_AIRCRAFT_ROUTES):
        if ac["icao24"] not in _ACTIVE_WAR_SCENARIO_AIRCRAFT:
            continue
        positions = _interp_route_with_altitude(ac["route"], ac["altitudes_m"], n_pos, rng)
        _validate_aircraft_positions(ac["callsign"], positions)
        base_time = _NOW - timedelta(hours=6, minutes=idx * 12)

        def _hdg(p0: tuple[float, float, float], p1: tuple[float, float, float]) -> float:
            return (math.degrees(math.atan2(p1[0] - p0[0], p1[1] - p0[1])) + 360) % 360

        for i, (lon, lat, alt) in enumerate(positions):
            dt = base_time + timedelta(minutes=i * 6)
            prev = positions[i - 1] if i > 0 else positions[0]
            nxt = positions[i + 1] if i < len(positions) - 1 else positions[-1]
            hdg = _hdg(prev, nxt)
            vertical_rate_ms = (nxt[2] - prev[2]) / 720 if len(positions) > 1 else 0.0

            eid = _eid("ac", ac["icao24"], dt.isoformat())
            events.append(CanonicalEvent(
                event_id=eid,
                source="opensky",
                source_type=SourceType.TELEMETRY,
                entity_type=EntityType.AIRCRAFT,
                entity_id=ac["icao24"],
                event_type=EventType.AIRCRAFT_POSITION,
                event_time=dt,
                geometry=_point(lon, lat),
                centroid=_point(lon, lat),
                altitude_m=round(alt, 0),
                confidence=0.91,
                attributes={
                    "icao24": ac["icao24"],
                    "callsign": ac["callsign"],
                    "origin_country": ac["country"],
                    "baro_altitude_m": round(alt),
                    "geo_altitude_m": round(alt + rng.gauss(0, 25)),
                    "velocity_ms": round(ac["speed_ms"] + rng.gauss(0, 8), 1),
                    "true_track_deg": round(hdg + rng.gauss(0, 2), 1) % 360,
                    "vertical_rate_ms": round(vertical_rate_ms, 2),
                    "origin_airport": ac["origin"],
                    "destination_airport": ac["destination"],
                    "on_ground": False,
                },
                normalization=_NORM,
                provenance=_PROV,
                correlation_keys=CorrelationKeys(
                    aoi_ids=[_AOI_ID],
                    icao24=ac["icao24"],
                    callsign=ac["callsign"],
                ),
                license=_LIC,
            ))
    return events


# ── GDELT contextual events ─────────────────────────────────────────────────

_GDELT_HEADLINES = [
    ("UAE reopens airspace after missile and drone threat over Dubai", "SECURITY_AIRSPACE;MISSILE_ACTIVITY", 55.12, 25.19, "AP", "Dubai Airspace"),
    ("Commercial shipping through Hormuz falls to a trickle after vessel strikes", "SHIPPING;SECURITY_MARITIME;ENERGY", 56.34, 26.18, "AP", "Strait of Hormuz"),
    ("War-risk insurers sharply raise premiums for Hormuz transits", "FINANCE_RISK;SHIPPING;ENERGY", 56.46, 26.56, "Reuters", "Inbound TSS"),
    ("Fujairah tank farm hit again as east-coast energy sites face drone attacks", "ENERGY;SECURITY_MILITARY;DRONE_ACTIVITY", 56.34, 25.13, "AP", "Fujairah Port"),
    ("Bandar Abbas approaches congest with vessels awaiting escorted windows", "LOGISTICS;SHIPPING;SECURITY_MARITIME", 56.18, 26.86, "Reuters", "Bandar Abbas Approaches"),
    ("Coalition debates defensive naval mission to reopen Hormuz traffic", "DEFENSE;DIPLOMACY;SHIPPING", 56.18, 26.02, "AP", "Outbound TSS"),
    ("Sanctioned and shadow-linked tankers dominate remaining Gulf movements", "SANCTIONS;SHIPPING;ENERGY", 55.92, 26.14, "Reuters", "Central Gulf Lanes"),
    ("Emergency convoy planning shifts cargo staging toward Khor Fakkan", "LOGISTICS;SECURITY_MARITIME;TRANSPORT", 56.37, 25.34, "Gulf News", "Khor Fakkan"),
    ("Abu Musa garrison activity increases as regional war widens", "SECURITY_MILITARY;CONFLICT", 55.03, 25.88, "AP", "Abu Musa"),
    ("Fuel buyers scramble as Hormuz chokehold pushes crude above $100", "ENERGY;MARKETS;SHIPPING", 56.46, 25.18, "AP", "Fujairah Anchorage"),
    ("Emergency logistics corridor reroutes relief cargo along Oman coast", "LOGISTICS;HUMANITARIAN;SHIPPING", 56.58, 25.26, "Gulf News", "Fujairah Corridor"),
    ("Bandar Abbas repair crews reinforce blast walls and quay-side shelters", "CONSTRUCTION;SECURITY_MILITARY;PORTS", 56.26, 27.08, "Reuters", "Bandar Abbas"),
    ("Mine-hunting drones considered for sea-lane clearance near Musandam", "DEFENSE;MINE_COUNTERMEASURES;SHIPPING", 56.62, 25.96, "AP", "Musandam Approaches"),
    ("Regional carriers divert flights as Gulf missile alerts persist", "AVIATION;SECURITY_AIRSPACE;TRANSPORT", 56.06, 25.48, "AP", "Doha-Muscat Air Corridor"),
    ("Jebel Ali throughput drops as insurers and crews avoid war-zone routing", "LOGISTICS;SHIPPING;FINANCE_RISK", 55.07, 25.10, "Reuters", "Jebel Ali"),
    ("Qeshm shoreline surveillance expands to monitor drone-launch activity", "SECURITY_MILITARY;ISR;DRONE_ACTIVITY", 56.94, 26.83, "Al Jazeera", "Qeshm Island"),
    ("Escort demand rises for tankers waiting east of the strait", "SHIPPING;SECURITY_MARITIME;ENERGY", 57.02, 25.38, "Reuters", "East Gulf of Oman"),
    ("Asian refiners draw strategic stocks as Hormuz closures tighten supply", "ENERGY;MARKETS;SUPPLY_CHAIN", 55.03, 25.05, "AP", "Jebel Ali"),
]


def _gdelt_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(77)

    for idx, (headline, themes, lon, lat, publication, location_name) in enumerate(_GDELT_HEADLINES):
        _validate_point_in_aoi(headline, lon, lat)
        dt = _NOW - timedelta(days=rng.randint(1, 25), hours=rng.randint(0, 23))
        eid = _eid("gdelt", str(idx), headline[:20])

        events.append(CanonicalEvent(
            event_id=eid,
            source="gdelt",
            source_type=SourceType.CONTEXT_FEED,
            entity_type=EntityType.NEWS_ARTICLE,
            entity_id=f"gdelt-{eid}",
            event_type=EventType.CONTEXTUAL_EVENT,
            event_time=dt,
            geometry=_point(lon, lat),
            centroid=_point(lon, lat),
            confidence=round(rng.uniform(0.5, 0.95), 2),
            attributes={
                "headline": headline,
                "url": f"https://gdelt.example.com/article/{eid}",
                "tone": round(rng.uniform(-5, 5), 2),
                "theme_codes": themes.split(";"),
                "source_publication": publication,
                "language": "en",
                "num_mentions": rng.randint(3, 50),
                "num_sources": rng.randint(1, 12),
                "location_name": location_name,
            },
            normalization=_NORM,
            provenance=_PROV,
            correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID]),
            license=_LIC,
        ))
    return events


# ── Imagery acquisition events ───────────────────────────────────────────────

_IMAGERY_SCENES = [
    ("Sentinel-2A", "copernicus-cdse", "sentinel-2-l2a", 56.34, 26.56, 0.34, 0.22, "Inbound TSS"),
    ("Sentinel-2B", "copernicus-cdse", "sentinel-2-l2a", 56.16, 25.98, 0.34, 0.22, "Outbound TSS"),
    ("Landsat-9", "usgs-landsat", "landsat-c2-l2", 56.34, 25.14, 0.36, 0.24, "Fujairah Port"),
    ("Sentinel-2A", "earth-search", "sentinel-2-l2a", 56.28, 27.06, 0.32, 0.22, "Bandar Abbas"),
    ("Sentinel-2B", "copernicus-cdse", "sentinel-2-l2a", 56.74, 26.58, 0.34, 0.20, "Qeshm South"),
    ("Landsat-9", "usgs-landsat", "landsat-c2-l2", 55.06, 25.08, 0.34, 0.24, "Jebel Ali"),
    ("Sentinel-2A", "earth-search", "sentinel-2-l2a", 56.62, 25.96, 0.28, 0.18, "Musandam Approaches"),
    ("Sentinel-2B", "copernicus-cdse", "sentinel-2-l2a", 56.46, 25.18, 0.28, 0.18, "Fujairah Anchorage"),
    ("Landsat-9", "usgs-landsat", "landsat-c2-l2", 55.03, 25.88, 0.26, 0.18, "Abu Musa"),
    ("Sentinel-2A", "earth-search", "sentinel-2-l2a", 55.70, 26.24, 0.34, 0.22, "Central Gulf Transit"),
    ("Sentinel-2B", "copernicus-cdse", "sentinel-2-l2a", 56.94, 25.36, 0.28, 0.18, "East Gulf of Oman"),
    ("Landsat-9", "usgs-landsat", "landsat-c2-l2", 55.40, 26.62, 0.34, 0.22, "Western Gulf Approaches"),
]

def _imagery_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(55)

    for i, (platform, source, collection, cx, cy, hw, hh, label) in enumerate(_IMAGERY_SCENES):
        _validate_point_in_aoi(label, cx, cy)
        dt = _NOW - timedelta(days=rng.randint(1, 28), hours=rng.randint(6, 14))
        cloud = round(rng.uniform(0, 30), 1)
        poly = _rect_polygon(cx, cy, hw, hh)
        eid = _eid("img", source, str(i), dt.isoformat())

        events.append(CanonicalEvent(
            event_id=eid,
            source=source,
            source_type=SourceType.IMAGERY_CATALOG,
            entity_type=EntityType.IMAGERY_SCENE,
            entity_id=f"{collection}/{eid}",
            event_type=EventType.IMAGERY_ACQUISITION,
            event_time=dt,
            geometry=poly,
            centroid=_point(cx, cy),
            confidence=round(1.0 - cloud / 100.0, 2),
            attributes={
                "platform": platform,
                "cloud_cover_pct": cloud,
                "gsd_m": 10.0 if "Sentinel" in platform else 30.0,
                "processing_level": "L2A",
                "bands_available": ["B02", "B03", "B04", "B08"] if "Sentinel" in platform else ["B2", "B3", "B4", "B5"],
                "scene_url": f"https://example.com/scenes/{eid}",
                "scene_label": label,
            },
            normalization=_NORM,
            provenance=_PROV,
            correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID]),
            license=_LIC,
        ))
    return events


# ── Public API ───────────────────────────────────────────────────────────────

def seed_aoi_store(store: AOIStore) -> str:
    """Create the Strait of Hormuz demo AOI. Returns the AOI id."""
    geometry = GeometryModel(
        type="Polygon",
        coordinates=[[ 
            [_LON_MIN, _LAT_MIN],
            [_LON_MAX, _LAT_MIN],
            [_LON_MAX, _LAT_MAX],
            [_LON_MIN, _LAT_MAX],
            [_LON_MIN, _LAT_MIN],
        ]],
    )
    aoi = store.create(AOICreate(
        name="Strait of Hormuz",
        geometry=geometry,
        description="Demo AOI covering the Strait of Hormuz and surrounding waters",
        tags=["demo", "maritime", "hormuz"],
    ))
    return aoi.id


def _signal_events() -> list[CanonicalEvent]:
    """Synthetic signal-intelligence events covering all 9 new connector types."""
    rng = random.Random(42)
    events: list[CanonicalEvent] = []

    def _pt(lon: float, lat: float) -> dict:
        return {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}

    def _add(
        prefix: str,
        index: int,
        source: str,
        source_type: SourceType,
        entity_type: EntityType,
        event_type: EventType,
        lon: float,
        lat: float,
        days_ago: int,
        attrs: dict,
    ) -> None:
        _validate_point_in_aoi(f"{source}:{event_type.value}", lon, lat)
        dt = _NOW - timedelta(days=days_ago, hours=rng.randint(0, 23))
        eid = _eid(prefix, str(index), source)
        events.append(CanonicalEvent(
            event_id=eid,
            source=source,
            source_type=source_type,
            entity_type=entity_type,
            entity_id=f"{source}/{eid}",
            event_type=event_type,
            event_time=dt,
            geometry=_pt(lon, lat),
            centroid=_pt(lon, lat),
            confidence=round(rng.uniform(0.65, 0.98), 2),
            attributes=attrs,
            normalization=_NORM,
            provenance=_PROV,
            correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID]),
            license=_LIC,
        ))

    # ── SEISMIC_EVENT (usgs-earthquake) ──────────────────────────────────────
    _seismic = [
        (56.80, 26.15, 2, {"magnitude": 3.8, "depth_km": 12.4, "magType": "ml"}),
        (55.50, 25.80, 7, {"magnitude": 4.2, "depth_km": 8.1,  "magType": "mb"}),
        (57.10, 26.90, 14, {"magnitude": 2.9, "depth_km": 15.0, "magType": "ml"}),
        (55.20, 26.60, 20, {"magnitude": 3.5, "depth_km": 22.0, "magType": "mb"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_seismic):
        _add("eq", i, "usgs-earthquake", SourceType.PUBLIC_RECORD,
             EntityType.SEISMIC_HAZARD, EventType.SEISMIC_EVENT, lon, lat, d, attrs)

    # ── NATURAL_HAZARD_EVENT (nasa-eonet) ─────────────────────────────────────
    _hazards = [
        (56.20, 25.50, 3,  {"title": "Sandstorm — Gulf of Oman", "category": "dustHaze", "eonet_id": "EONET_7001"}),
        (55.80, 27.10, 9,  {"title": "Flash Flood — Muscat region", "category": "floods", "eonet_id": "EONET_7002"}),
        (56.90, 26.40, 18, {"title": "Cyclone Remnant — Arabian Sea", "category": "severestorms", "eonet_id": "EONET_7003"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_hazards):
        _add("hz", i, "nasa-eonet", SourceType.PUBLIC_RECORD,
             EntityType.NATURAL_HAZARD, EventType.NATURAL_HAZARD_EVENT, lon, lat, d, attrs)

    # ── WEATHER_OBSERVATION (open-meteo) ─────────────────────────────────────
    _weather_pts = [
        (55.95, 26.35, 0,  {"temperature_c": 38.2, "wind_speed_kmh": 24, "humidity_pct": 55, "condition": "clear"}),
        (56.50, 25.10, 1,  {"temperature_c": 40.1, "wind_speed_kmh": 18, "humidity_pct": 48, "condition": "hazy"}),
        (54.95, 26.80, 2,  {"temperature_c": 36.5, "wind_speed_kmh": 32, "humidity_pct": 62, "condition": "dusty"}),
        (57.30, 25.60, 3,  {"temperature_c": 37.8, "wind_speed_kmh": 15, "humidity_pct": 51, "condition": "clear"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_weather_pts):
        _add("wx", i, "open-meteo", SourceType.PUBLIC_RECORD,
             EntityType.SYSTEM, EventType.WEATHER_OBSERVATION, lon, lat, d, attrs)

    # ── CONFLICT_EVENT (acled) ────────────────────────────────────────────────
    _conflicts = [
        (56.10, 26.05, 5,  {"event_type": "Explosions/Remote violence", "actor1": "Iranian strike package", "fatalities": 0, "notes": "Missile debris fell near an outbound convoy lane after air-defense intercepts."}),
        (55.60, 25.40, 11, {"event_type": "Strategic developments", "actor1": "Regional naval task force", "fatalities": 0, "notes": "Emergency escort pattern activated for tankers diverting to Fujairah."}),
        (57.20, 26.70, 16, {"event_type": "Violence against civilians", "actor1": "Unknown armed actors", "fatalities": 1, "notes": "Crew casualty reported after a strike on a merchant vessel east of the strait."}),
        (55.10, 26.20, 22, {"event_type": "Explosions/Remote violence", "actor1": "One-way attack drones", "fatalities": 0, "notes": "Drone swarm intercepted near a commercial shipping concentration area."}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_conflicts):
        _add("cfl", i, "acled", SourceType.PUBLIC_RECORD,
             EntityType.CONFLICT_INCIDENT, EventType.CONFLICT_EVENT, lon, lat, d, attrs)

    # ── MARITIME_WARNING (nga-msi) ────────────────────────────────────────────
    _msi_warnings = [
        (56.65, 26.55, 4,  {"navarea": "IX", "number": "202/2026", "subtype": "MISSILE / DRONE THREAT", "text": "Commercial traffic report missile and drone activity in the inbound escorted lane."}),
        (55.75, 25.95, 10, {"navarea": "IX", "number": "185/2026", "subtype": "ESCORTED TRANSIT ONLY", "text": "Southbound transits require convoy assignment and positive routing clearance."}),
        (57.00, 25.20, 17, {"navarea": "IX", "number": "174/2026", "subtype": "MINE COUNTERMEASURE OPS", "text": "Defensive clearance and surveillance operations active near eastern approaches."}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_msi_warnings):
        _add("msi", i, "nga-msi", SourceType.PUBLIC_RECORD,
             EntityType.MARITIME_ZONE, EventType.MARITIME_WARNING, lon, lat, d, attrs)

    # ── MILITARY_SITE_OBSERVATION (osm-military) ──────────────────────────────
    _mil_sites = [
        (55.48, 25.30, 30, {"osm_id": 123456, "military": "airfield", "name": "Al Minhad AB vicinity"}),
        (56.15, 27.15, 30, {"osm_id": 234567, "military": "naval_base", "name": "Bandar Abbas naval base"}),
        (56.78, 26.48, 30, {"osm_id": 345678, "military": "range", "name": "Firing range — Qeshm Island"}),
        (55.02, 26.95, 30, {"osm_id": 456789, "military": "bunker", "name": "Hardened facility detected"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_mil_sites):
        _add("mil", i, "osm-military", SourceType.PUBLIC_RECORD,
             EntityType.MILITARY_INSTALLATION, EventType.MILITARY_SITE_OBSERVATION, lon, lat, d, attrs)

    # ── THERMAL_ANOMALY_EVENT (nasa-firms) ────────────────────────────────────
    _fires = [
        (56.35, 25.70, 1,  {"frp_mw": 28.4, "confidence": "high", "satellite": "AQUA", "type": "Presumed Vegetation Fire"}),
        (55.90, 26.80, 3,  {"frp_mw": 145.2, "confidence": "high", "satellite": "TERRA", "type": "Offshore Platform Flare"}),
        (57.15, 26.10, 6,  {"frp_mw": 12.1, "confidence": "nominal", "satellite": "AQUA", "type": "Presumed Vegetation Fire"}),
        (54.92, 25.50, 9,  {"frp_mw": 67.8, "confidence": "high", "satellite": "VIIRS", "type": "Industrial Flare"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_fires):
        _add("fire", i, "nasa-firms", SourceType.PUBLIC_RECORD,
             EntityType.THERMAL_ANOMALY, EventType.THERMAL_ANOMALY_EVENT, lon, lat, d, attrs)

    # ── SPACE_WEATHER_EVENT (noaa-swpc) ───────────────────────────────────────
    # Space weather has no geographic location — use centroid of the AOI
    _space_wx = [
        (56.13, 26.15, 4,  {"kp_index": 4, "classification": "G1-Minor", "source": "CME", "description": "Minor geomagnetic storm watch"}),
        (56.13, 26.15, 12, {"kp_index": 6, "classification": "G2-Moderate", "source": "Solar Flare X1.2", "description": "Moderate geomagnetic storm in progress"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_space_wx):
        _add("swx", i, "noaa-swpc", SourceType.PUBLIC_RECORD,
             EntityType.SPACE_WEATHER_PHENOMENON, EventType.SPACE_WEATHER_EVENT, lon, lat, d, attrs)

    # ── AIR_QUALITY_OBSERVATION (openaq) ─────────────────────────────────────
    _aq = [
        (55.38, 25.26, 0,  {"pm25_ugm3": 42.1, "pm10_ugm3": 98.0,  "aqi": 115, "city": "Dubai vicinity", "parameter": "pm25"}),
        (56.27, 27.18, 1,  {"pm25_ugm3": 61.5, "pm10_ugm3": 143.0, "aqi": 152, "city": "Bandar Abbas", "parameter": "pm25"}),
        (57.10, 25.35, 2,  {"pm25_ugm3": 18.3, "pm10_ugm3": 45.0,  "aqi": 65,  "city": "Muscat coast", "parameter": "pm25"}),
        (55.52, 26.10, 3,  {"pm25_ugm3": 55.2, "pm10_ugm3": 120.0, "aqi": 141, "city": "Abu Dhabi offshore", "parameter": "pm25"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_aq):
        _add("aq", i, "openaq", SourceType.PUBLIC_RECORD,
             EntityType.AIR_QUALITY_SENSOR, EventType.AIR_QUALITY_OBSERVATION, lon, lat, d, attrs)

    return events


def _operational_events() -> list[CanonicalEvent]:
    """Priority analyst events for the amber map overlay."""
    rng = random.Random(144)
    events: list[CanonicalEvent] = []

    def _add(
        prefix: str,
        index: int,
        event_type: EventType,
        lon: float,
        lat: float,
        days_ago: int,
        entity_type: EntityType,
        attrs: dict,
        source: str = "regional-ops",
        source_type: SourceType = SourceType.PUBLIC_RECORD,
    ) -> None:
        _validate_point_in_aoi(f"{source}:{event_type.value}", lon, lat)
        dt = _NOW - timedelta(days=days_ago, hours=rng.randint(0, 20))
        eid = _eid(prefix, str(index), event_type.value, dt.isoformat())
        point = _point(lon, lat)
        events.append(CanonicalEvent(
            event_id=eid,
            source=source,
            source_type=source_type,
            entity_type=entity_type,
            entity_id=f"{event_type.value}/{eid}",
            event_type=event_type,
            event_time=dt,
            geometry=point,
            centroid=point,
            confidence=round(rng.uniform(0.74, 0.97), 2),
            attributes=attrs,
            normalization=_NORM,
            provenance=_PROV,
            correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID]),
            license=_LIC,
        ))

    amber_events = [
        (EventType.PERMIT_EVENT, 55.18, 25.27, 2, EntityType.PERMIT, {
            "permit_number": "DXB-PORT-2026-1184",
            "applicant": "Gulf Convoy Coordination Cell",
            "permit_type": "Escorted Transit Slot",
            "status": "Approved",
            "authority": "Dubai Maritime Security Cell",
            "description": "Protected departure window issued for a tanker joining the next escorted westbound convoy.",
        }),
        (EventType.INSPECTION_EVENT, 56.11, 26.04, 1, EntityType.PERMIT, {
            "permit_number": "OMN-PSC-2026-041",
            "applicant": "Emergency Port State Control",
            "permit_type": "Post-Strike Hull Inspection",
            "status": "Scheduled",
            "authority": "Oman Coast Guard",
            "description": "Boarding team queued after shrapnel damage was reported during a southbound transit through the threat corridor.",
        }),
        (EventType.PROJECT_EVENT, 56.92, 26.78, 6, EntityType.CONSTRUCTION_SITE, {
            "permit_number": "IRN-INFRA-2026-228",
            "applicant": "Bandar Abbas Emergency Works Office",
            "permit_type": "Blast Wall Reinforcement",
            "status": "Active",
            "authority": "Ports and Maritime Organization",
            "description": "Rapid hardening project underway to protect tanker holding areas and quay-side fuel infrastructure.",
        }),
        (EventType.COMPLAINT_EVENT, 55.74, 25.94, 4, EntityType.PERMIT, {
            "permit_number": "MSI-CASE-2026-092",
            "applicant": "Convoy Scheduling Desk",
            "permit_type": "Transit Delay Hazard",
            "status": "Open",
            "authority": "Regional Vessel Traffic Service",
            "description": "Repeated complaints cite vessels holding too close to the outbound lane while awaiting escorted passage slots.",
        }),
        (EventType.PERMIT_EVENT, 57.06, 25.19, 3, EntityType.PERMIT, {
            "permit_number": "MCT-FLT-2026-077",
            "applicant": "Civil Air Mobility Coordination",
            "permit_type": "Emergency Relief Air Corridor",
            "status": "Approved",
            "authority": "Civil Aviation Affairs",
            "description": "Temporary low-level corridor approved for relief flights supporting displaced crews and east-coast energy workers.",
        }),
        (EventType.INSPECTION_EVENT, 55.46, 26.62, 5, EntityType.PERMIT, {
            "permit_number": "UAE-CST-2026-309",
            "applicant": "Customs & Sanctions Cell",
            "permit_type": "Manifest Integrity Review",
            "status": "In Progress",
            "authority": "Federal Customs Authority",
            "description": "High-priority boarding triggered after ownership records shifted during a restricted-routing declaration.",
        }),
        (EventType.PROJECT_EVENT, 56.44, 25.69, 8, EntityType.CONSTRUCTION_SITE, {
            "permit_number": "FJR-ENG-2026-188",
            "applicant": "Fujairah Energy Emergency Office",
            "permit_type": "Tank Farm Repair",
            "status": "Mobilizing",
            "authority": "Fujairah Port Authority",
            "description": "Rapid repair crews staging near the anchorage after repeated drone and missile impacts on storage assets.",
        }),
        (EventType.COMPLAINT_EVENT, 56.52, 26.56, 2, EntityType.PERMIT, {
            "permit_number": "HRMZ-OPS-2026-204",
            "applicant": "Watchfloor Duty Officer",
            "permit_type": "AIS Blackout in Threat Corridor",
            "status": "Escalated",
            "authority": "Regional Maritime Fusion Cell",
            "description": "Analyst complaint filed after repeated AIS dropout inside the inbound escorted lane during missile warning periods.",
        }),
        (EventType.PERMIT_EVENT, 55.94, 26.84, 7, EntityType.PERMIT, {
            "permit_number": "IRN-SHP-2026-144",
            "applicant": "Bandar Abbas Harbor Control",
            "permit_type": "Protected Anchorage Window",
            "status": "Approved",
            "authority": "Qeshm Free Zone",
            "description": "Sheltered holding area allocated for tankers waiting on escort confirmation into Bandar Abbas approaches.",
        }),
        (EventType.INSPECTION_EVENT, 56.78, 26.42, 9, EntityType.PERMIT, {
            "permit_number": "QSM-RNG-2026-011",
            "applicant": "Coastal Security Directorate",
            "permit_type": "Drone Launch Shoreline Sweep",
            "status": "Closed",
            "authority": "Island Security Directorate",
            "description": "Shoreline sweep completed after surveillance detected repeated unmanned-launch signatures near a restricted coastal zone.",
        }),
        (EventType.PROJECT_EVENT, 55.08, 26.96, 12, EntityType.CONSTRUCTION_SITE, {
            "permit_number": "ADH-MRN-2026-064",
            "applicant": "Emergency Maritime Support Office",
            "permit_type": "Expeditionary Pier Hardening",
            "status": "Approved",
            "authority": "Abu Dhabi Ports",
            "description": "Temporary hardening package approved for a fallback logistics pier supporting escorted energy departures.",
        }),
        (EventType.COMPLAINT_EVENT, 57.22, 25.44, 1, EntityType.PERMIT, {
            "permit_number": "MUS-AIR-2026-055",
            "applicant": "Airspace Coordination Cell",
            "permit_type": "Missile Threat Air Corridor",
            "status": "Open",
            "authority": "Muscat ACC",
            "description": "Complaint logged after repeated reroutes pushed civilian traffic toward an active missile-warning corridor over the Gulf of Oman.",
        }),
    ]

    for idx, (event_type, lon, lat, days_ago, entity_type, attrs) in enumerate(amber_events):
        _add(f"ops{idx}", idx, event_type, lon, lat, days_ago, entity_type, attrs)

    return events


def seed_event_store(store: EventStore, aoi_id: str | None = None) -> int:
    """Populate the EventStore with synthetic demo data. Returns event count."""
    if aoi_id:
        global _AOI_ID
        _AOI_ID = aoi_id

    all_events: list[CanonicalEvent] = []
    all_events.extend(_ship_events())
    all_events.extend(_aircraft_events())
    all_events.extend(_gdelt_events())
    all_events.extend(_imagery_events())
    all_events.extend(_signal_events())
    all_events.extend(_operational_events())

    store.ingest_batch(all_events)
    return len(all_events)
