"""Seed the in-memory EventStore with realistic synthetic data for the demo.

Generates ship tracks, flight tracks, GDELT contextual events, and imagery
acquisition events in the Strait of Hormuz area so the UI has data to render
immediately on startup.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from typing import List

from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    EntityType,
)
from src.services.event_store import EventStore
from src.services.aoi_store import AOIStore
from src.models.aoi import AOICreate

# AOI: Strait of Hormuz bounding box
_LON_MIN, _LON_MAX = 54.83, 57.44
_LAT_MIN, _LAT_MAX = 24.99, 27.32
_AOI_ID = "5bc84ca9-a46b-47e9-a735-8fd000fd3123"

_NORM = NormalizationRecord(normalized_by="demo-seeder")
_PROV = ProvenanceRecord(raw_source_ref="demo://seeder")
_LIC = LicenseRecord()
_NOW = datetime.now(timezone.utc)


def _eid(prefix: str, *parts: str) -> str:
    h = hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]
    return f"{prefix}-{h}"


def _point(lon: float, lat: float) -> dict:
    return {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}


# ── Ship tracks ──────────────────────────────────────────────────────────────

_SHIPS = [
    {"mmsi": "211330000", "name": "EVER GRACE", "type": 70, "dest": "Bandar Abbas"},
    {"mmsi": "477123400", "name": "PACIFIC VOYAGER", "type": 80, "dest": "Fujairah"},
    {"mmsi": "636017432", "name": "STELLA MARINER", "type": 70, "dest": "Jebel Ali"},
    {"mmsi": "538006712", "name": "ORIENT PEARL", "type": 80, "dest": "Muscat"},
    {"mmsi": "249987000", "name": "CASPIAN PRIDE", "type": 70, "dest": "Khor Fakkan"},
    {"mmsi": "215631000", "name": "GULF BREEZE", "type": 60, "dest": "Dubai"},
    {"mmsi": "352456000", "name": "HORMUZ CARRIER", "type": 70, "dest": "Abu Dhabi"},
    {"mmsi": "440123456", "name": "EASTERN STAR", "type": 80, "dest": "Sharjah"},
]


def _ship_events() -> List[CanonicalEvent]:
    events: List[CanonicalEvent] = []
    rng = random.Random(42)

    for ship in _SHIPS:
        # Each ship: 60 position reports over last 12 hours
        base_lon = rng.uniform(_LON_MIN + 0.3, _LON_MAX - 0.3)
        base_lat = rng.uniform(_LAT_MIN + 0.3, _LAT_MAX - 0.3)
        heading = rng.uniform(30, 330)
        speed_kn = rng.uniform(8, 16)
        base_time = _NOW - timedelta(hours=12)

        for i in range(60):
            dt = base_time + timedelta(minutes=i * 12)
            # Move ship along heading
            dx = math.cos(math.radians(heading)) * speed_kn * 0.002 * i
            dy = math.sin(math.radians(heading)) * speed_kn * 0.001 * i
            lon = base_lon + dx + rng.gauss(0, 0.005)
            lat = base_lat + dy + rng.gauss(0, 0.003)
            lon = max(_LON_MIN, min(_LON_MAX, lon))
            lat = max(_LAT_MIN, min(_LAT_MAX, lat))

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
                    "ship_type": ship["type"],
                    "speed_kn": round(speed_kn + rng.gauss(0, 1), 1),
                    "course_deg": round(heading + rng.gauss(0, 5), 1) % 360,
                    "heading_deg": round(heading, 1),
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


def _aircraft_events() -> List[CanonicalEvent]:
    events: List[CanonicalEvent] = []
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


def _gdelt_events() -> List[CanonicalEvent]:
    events: List[CanonicalEvent] = []
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

def _imagery_events() -> List[CanonicalEvent]:
    events: List[CanonicalEvent] = []
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


def seed_event_store(store: EventStore, aoi_id: str | None = None) -> int:
    """Populate the EventStore with synthetic demo data. Returns event count."""
    if aoi_id:
        global _AOI_ID
        _AOI_ID = aoi_id

    all_events: List[CanonicalEvent] = []
    all_events.extend(_ship_events())
    all_events.extend(_aircraft_events())
    all_events.extend(_gdelt_events())
    all_events.extend(_imagery_events())

    store.ingest_batch(all_events)
    return len(all_events)
