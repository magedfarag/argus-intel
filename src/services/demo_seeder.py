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

from src.models.aoi import AOICreate
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


# ── Ship tracks ──────────────────────────────────────────────────────────────
# Each route is a list of (lon, lat) waypoints that follow real maritime
# channels in the Strait of Hormuz Traffic Separation Scheme (TSS).
# Inbound lane (into Persian Gulf): north of Musandam Peninsula, ~26.35–26.55°N
# Outbound lane (to Gulf of Oman): south of Musandam, ~26.0–26.25°N
# The Musandam Peninsula tip is at ~56.35°E, 26.32°N — routes stay clear of it.

_SHIP_ROUTES = [
    # ── Inbound routes (Gulf of Oman → Persian Gulf, north channel) ──────────
    # All inbound routes must be at lat > 26.5 when lon is in [56.1, 56.7] to
    # clear the Musandam Peninsula.  The "corner" waypoint at ~(56.75, 26.45)
    # positions the vessel north of the peninsula BEFORE the interpolation
    # enters the critical longitude band.
    {
        "mmsi": "211330000", "name": "EVER GRACE", "ship_type": 70,
        "dest": "Bandar Abbas", "speed_kn": 13.5,
        "route": [
            (57.15, 25.70), (56.98, 25.92), (56.82, 26.18),
            (56.75, 26.45), (56.68, 26.55), (56.35, 26.62),
            (55.95, 26.62), (55.55, 26.65), (55.05, 26.80),
        ],
    },
    {
        "mmsi": "636017432", "name": "STELLA MARINER", "ship_type": 70,
        "dest": "Jebel Ali", "speed_kn": 12.0,
        "route": [
            (57.30, 25.52), (57.08, 25.78), (56.88, 26.05),
            (56.78, 26.35), (56.72, 26.52), (56.42, 26.60),
            (55.98, 26.58), (55.58, 26.63), (55.10, 26.83),
        ],
    },
    {
        "mmsi": "352456000", "name": "HORMUZ CARRIER", "ship_type": 70,
        "dest": "Abu Dhabi", "speed_kn": 11.5,
        "route": [
            (57.05, 26.08), (56.88, 26.22), (56.78, 26.42),
            (56.70, 26.55), (56.38, 26.62), (56.05, 26.65),
            (55.65, 26.62), (55.25, 26.73),
        ],
    },
    # ── Outbound routes (Persian Gulf → Gulf of Oman, south channel) ─────────
    # All outbound routes must be at lat < 26.1 when lon is in [56.1, 56.7].
    {
        "mmsi": "477123400", "name": "PACIFIC VOYAGER", "ship_type": 80,
        "dest": "Fujairah", "speed_kn": 14.0,
        "route": [
            (55.12, 26.70), (55.42, 26.48), (55.78, 26.22),
            (56.12, 26.02), (56.50, 25.78), (56.88, 25.52), (57.20, 25.28),
        ],
    },
    {
        "mmsi": "538006712", "name": "ORIENT PEARL", "ship_type": 80,
        "dest": "Muscat", "speed_kn": 12.5,
        "route": [
            (55.02, 26.58), (55.38, 26.36), (55.72, 26.12),
            (56.08, 25.92), (56.48, 25.68), (56.85, 25.42), (57.18, 25.12),
        ],
    },
    {
        "mmsi": "440123456", "name": "EASTERN STAR", "ship_type": 80,
        "dest": "Sharjah", "speed_kn": 10.5,
        "route": [
            (55.20, 26.65), (55.52, 26.42), (55.85, 26.18),
            (56.18, 25.98), (56.55, 25.72), (56.92, 25.48),
        ],
    },
    # ── Iran coast route (Bandar Abbas area, staying near 27°N) ─────────────
    {
        "mmsi": "249987000", "name": "CASPIAN PRIDE", "ship_type": 70,
        "dest": "Khor Fakkan", "speed_kn": 9.0,
        "route": [
            (55.28, 27.08), (55.70, 27.02), (56.10, 26.95),
            (56.52, 26.90), (56.92, 26.82), (57.25, 26.78),
        ],
    },
    # ── Gulf of Oman coastal (Khor Fakkan → north, staying offshore) ─────────
    {
        "mmsi": "215631000", "name": "GULF BREEZE", "ship_type": 60,
        "dest": "Dubai", "speed_kn": 8.5,
        "route": [
            (57.28, 25.18), (57.00, 25.22), (56.72, 25.28),
            (56.48, 25.38), (56.28, 25.55), (56.10, 25.80), (55.88, 26.08),
        ],
    },
    # ── Additional vessels for richer demo ───────────────────────────────────
    {
        # VLCC tanker, outbound loaded, slow — south outbound lane
        "mmsi": "466001000", "name": "AL ZUBARA", "ship_type": 80,
        "dest": "Ras Laffan", "speed_kn": 11.0,
        "route": [
            (55.05, 26.55), (55.32, 26.32), (55.65, 26.08),
            (56.02, 25.88), (56.42, 25.62), (56.82, 25.35), (57.22, 25.05),
        ],
    },
    {
        # LPG carrier, inbound toward Bandar Abbas — north channel
        "mmsi": "422002000", "name": "JAHAN HEROES", "ship_type": 70,
        "dest": "Bandar Abbas", "speed_kn": 12.5,
        "route": [
            (57.38, 25.48), (57.15, 25.75), (56.95, 26.02),
            (56.80, 26.30), (56.72, 26.52), (56.45, 26.62),
            (56.10, 26.72), (55.72, 26.88), (55.42, 27.02),
        ],
    },
    {
        # Container feeder, inbound toward Dubai — north channel via Qeshm narrows
        "mmsi": "371002000", "name": "KHOR DUBAI", "ship_type": 70,
        "dest": "Jebel Ali", "speed_kn": 13.0,
        "route": [
            (57.42, 25.62), (57.18, 25.88), (56.95, 26.15),
            (56.78, 26.38), (56.70, 26.55), (56.38, 26.65),
            (55.95, 26.68), (55.52, 26.72), (55.12, 26.85),
        ],
    },
]


def _interp_route(
    waypoints: list[tuple[float, float]],
    n_points: int,
    rng: random.Random,
    jitter_lon: float = 0.001,
    jitter_lat: float = 0.001,
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
    n_pos = 90       # position reports per vessel
    window_h = 30    # hours covered

    for ship in _SHIP_ROUTES:
        base_time = _NOW - timedelta(hours=window_h)
        positions = _interp_route(ship["route"], n_pos, rng)

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
                confidence=0.95,
                attributes={
                    "mmsi": ship["mmsi"],
                    "vessel_name": ship["name"],
                    "ship_type": ship["ship_type"],
                    "speed_kn": round(speed_kn + rng.gauss(0, 0.5), 1),
                    "course_deg": round(hdg + rng.gauss(0, 3), 1) % 360,
                    "heading_deg": round(hdg, 1),
                    "destination": ship["dest"],
                },
                normalization=_NORM,
                provenance=_PROV,
                correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID], mmsi=ship["mmsi"]),
                license=_LIC,
            ))
    return events


# ── Flight tracks ────────────────────────────────────────────────────────────

_AIRCRAFT = [
    {"icao24": "710112", "callsign": "QTR802", "country": "Qatar"},
    {"icao24": "896340", "callsign": "UAE567", "country": "United Arab Emirates"},
    {"icao24": "730003", "callsign": "IRA412", "country": "Iran"},
    {"icao24": "7107a2", "callsign": "GFA215", "country": "Bahrain"},
    {"icao24": "71be12", "callsign": "OMA643", "country": "Oman"},
    {"icao24": "710501", "callsign": "QTR916", "country": "Qatar"},
]


def _aircraft_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(99)

    for ac in _AIRCRAFT:
        base_lon = rng.uniform(_LON_MIN + 0.5, _LON_MAX - 0.5)
        base_lat = rng.uniform(_LAT_MIN + 0.5, _LAT_MAX - 0.5)
        heading = rng.uniform(0, 360)
        speed = rng.uniform(200, 400)  # m/s
        alt = rng.uniform(8000, 12000)
        base_time = _NOW - timedelta(hours=6)

        for i in range(40):
            dt = base_time + timedelta(minutes=i * 9)
            dx = math.cos(math.radians(heading)) * 0.004 * i
            dy = math.sin(math.radians(heading)) * 0.003 * i
            lon = base_lon + dx + rng.gauss(0, 0.002)
            lat = base_lat + dy + rng.gauss(0, 0.002)
            lon = max(_LON_MIN, min(_LON_MAX, lon))
            lat = max(_LAT_MIN, min(_LAT_MAX, lat))

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
                altitude_m=round(alt + rng.gauss(0, 50), 0),
                confidence=0.9,
                attributes={
                    "icao24": ac["icao24"],
                    "callsign": ac["callsign"],
                    "origin_country": ac["country"],
                    "baro_altitude_m": round(alt + rng.gauss(0, 50)),
                    "velocity_ms": round(speed + rng.gauss(0, 10), 1),
                    "true_track_deg": round(heading + rng.gauss(0, 3), 1) % 360,
                    "on_ground": False,
                },
                normalization=_NORM,
                provenance=_PROV,
                correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID], icao24=ac["icao24"], callsign=ac["callsign"]),
                license=_LIC,
            ))
    return events


# ── GDELT contextual events ─────────────────────────────────────────────────

_GDELT_HEADLINES = [
    ("Major port expansion announced in Fujairah", "ECON_TRADE;CONSTRUCTION"),
    ("UAE approves new industrial zone near Jebel Ali", "ECON_DEVELOPMENT;CONSTRUCTION"),
    ("Iran-Oman submarine cable project begins", "INFRA_UNDERWATER;CONSTRUCTION"),
    ("Shipping traffic surge through Strait of Hormuz", "ECON_TRADE;SHIPPING"),
    ("New desalination plant breaks ground near Bandar Abbas", "INFRA_WATER;CONSTRUCTION"),
    ("Oman Coast Guard increases maritime patrols", "SECURITY_MARITIME;DEFENSE"),
    ("GCC ministers discuss cross-border rail link", "INFRA_TRANSPORT;DIPLOMACY"),
    ("Dubai Port World reports record container throughput", "ECON_TRADE;LOGISTICS"),
    ("Environmental survey of Qeshm Island mangroves completed", "ENV_CONSERVATION;SCIENCE"),
    ("New military facility detected on Abu Musa island", "SECURITY_MILITARY;CONSTRUCTION"),
]


def _gdelt_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(77)

    for idx, (headline, themes) in enumerate(_GDELT_HEADLINES):
        dt = _NOW - timedelta(days=rng.randint(1, 25), hours=rng.randint(0, 23))
        lon = rng.uniform(_LON_MIN + 0.2, _LON_MAX - 0.2)
        lat = rng.uniform(_LAT_MIN + 0.2, _LAT_MAX - 0.2)
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
                "source_publication": rng.choice(["Al Jazeera", "Gulf News", "Reuters", "AP"]),
                "language": "en",
                "num_mentions": rng.randint(3, 50),
                "num_sources": rng.randint(1, 12),
            },
            normalization=_NORM,
            provenance=_PROV,
            correlation_keys=CorrelationKeys(aoi_ids=[_AOI_ID]),
            license=_LIC,
        ))
    return events


# ── Imagery acquisition events ───────────────────────────────────────────────

def _imagery_events() -> list[CanonicalEvent]:
    events: list[CanonicalEvent] = []
    rng = random.Random(55)

    platforms = [
        ("Sentinel-2A", "copernicus-cdse", "sentinel-2-l2a"),
        ("Sentinel-2B", "copernicus-cdse", "sentinel-2-l2a"),
        ("Landsat-9", "usgs-landsat", "landsat-c2-l2"),
        ("Sentinel-2A", "earth-search", "sentinel-2-l2a"),
    ]

    for i in range(12):
        platform, source, collection = platforms[i % len(platforms)]
        dt = _NOW - timedelta(days=rng.randint(1, 28), hours=rng.randint(6, 14))
        cloud = round(rng.uniform(0, 30), 1)

        # Footprint polygon
        cx = rng.uniform(_LON_MIN + 0.5, _LON_MAX - 0.5)
        cy = rng.uniform(_LAT_MIN + 0.5, _LAT_MAX - 0.5)
        hw, hh = 0.4, 0.3
        poly = {
            "type": "Polygon",
            "coordinates": [[
                [round(cx - hw, 5), round(cy - hh, 5)],
                [round(cx + hw, 5), round(cy - hh, 5)],
                [round(cx + hw, 5), round(cy + hh, 5)],
                [round(cx - hw, 5), round(cy + hh, 5)],
                [round(cx - hw, 5), round(cy - hh, 5)],
            ]],
        }
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
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [_LON_MIN, _LAT_MIN],
            [_LON_MAX, _LAT_MIN],
            [_LON_MAX, _LAT_MAX],
            [_LON_MIN, _LAT_MAX],
            [_LON_MIN, _LAT_MIN],
        ]],
    }
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
        (56.10, 26.05, 5,  {"event_type": "Protests", "actor1": "Protesters", "fatalities": 0, "notes": "Peaceful demonstration"}),
        (55.60, 25.40, 11, {"event_type": "Explosions/Remote violence", "actor1": "Armed group", "fatalities": 2, "notes": "IED incident near transport route"}),
        (57.20, 26.70, 16, {"event_type": "Violence against civilians", "actor1": "Unknown armed actors", "fatalities": 1, "notes": "Incident reported"}),
        (55.10, 26.20, 22, {"event_type": "Strategic developments", "actor1": "Naval forces", "fatalities": 0, "notes": "Vessel interception reported"}),
    ]
    for i, (lon, lat, d, attrs) in enumerate(_conflicts):
        _add("cfl", i, "acled", SourceType.PUBLIC_RECORD,
             EntityType.CONFLICT_INCIDENT, EventType.CONFLICT_EVENT, lon, lat, d, attrs)

    # ── MARITIME_WARNING (nga-msi) ────────────────────────────────────────────
    _msi_warnings = [
        (56.65, 26.55, 4,  {"navarea": "IX", "number": "202/2026", "subtype": "DRIFTING HAZARD", "text": "Drifting container reported in TSS inbound lane"}),
        (55.75, 25.95, 10, {"navarea": "IX", "number": "185/2026", "subtype": "MILITARY EXERCISE", "text": "Naval exercise zone active 0600-1800 UTC"}),
        (57.00, 25.20, 17, {"navarea": "IX", "number": "174/2026", "subtype": "SUBMARINE CABLE", "text": "Survey vessel operations — keep clear 500m"}),
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

    store.ingest_batch(all_events)
    return len(all_events)
