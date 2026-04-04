"""Phase 1 Track B: provenance.raw_source_ref population tests.

Verifies that every connector's normalize() emits a non-empty,
entity-specific raw_source_ref so polled data is replayable.

Connectors checked:
- AIS (ais_stream.py)   → ais://mmsi/{mmsi}@{iso_ts}
- OpenSky (opensky.py)  → opensky://icao24/{icao}@{iso_ts}
- GDELT (gdelt.py)      → gdelt://doc/{url_hash}
- STAC via earth_search → stac://earth-search/{item_id}

Track segments are also verified:
- AIS track segment     → ais://mmsi/{mmsi}/track@{iso_ts}
- OpenSky track segment → opensky://icao24/{icao}/track@{iso_ts}
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

_T0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 4, 1, 10, 5, 0, tzinfo=timezone.utc)

# ── AIS ───────────────────────────────────────────────────────────────────────


def _ais_msg(mmsi: str = "123456789", lat: float = 24.8, lon: float = 46.67) -> Dict[str, Any]:
    ts = _T0.isoformat()
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": "TEST", "time_utc": ts},
        "Message": {
            "PositionReport": {
                "UserID": int(mmsi),
                "Latitude": lat,
                "Longitude": lon,
                "SpeedOverGround": 5.0,
                "CourseOverGround": 90.0,
                "NavigationalStatus": 0,
                "TrueHeading": 90,
            }
        },
        "_fetched_at": ts,
    }


class TestAisRawSourceRef:
    def setup_method(self) -> None:
        from src.connectors.ais_stream import AisStreamConnector
        self.conn = AisStreamConnector(api_key="test-key")

    def test_normalize_sets_entity_specific_ref(self) -> None:
        ev = self.conn.normalize(_ais_msg(mmsi="111222333"))
        ref = ev.provenance.raw_source_ref
        assert ref.startswith("ais://mmsi/111222333@"), f"Unexpected ref: {ref!r}"
        assert ref != "ais://stream.aisstream.io/position"

    def test_ref_contains_mmsi(self) -> None:
        ev = self.conn.normalize(_ais_msg(mmsi="987654321"))
        assert "987654321" in ev.provenance.raw_source_ref

    def test_ref_is_nonempty(self) -> None:
        ev = self.conn.normalize(_ais_msg())
        assert ev.provenance.raw_source_ref

    def test_different_mmsi_gives_different_ref(self) -> None:
        ev1 = self.conn.normalize(_ais_msg(mmsi="111111111"))
        ev2 = self.conn.normalize(_ais_msg(mmsi="222222222"))
        assert ev1.provenance.raw_source_ref != ev2.provenance.raw_source_ref

    def test_track_segment_ref_contains_mmsi_and_track(self) -> None:
        from src.connectors.ais_stream import AisStreamConnector
        conn = AisStreamConnector(api_key="test-key")
        msg1 = _ais_msg(mmsi="555666777", lat=24.80, lon=46.67)
        msg2 = {**_ais_msg(mmsi="555666777", lat=24.81, lon=46.68),
                "MetaData": {"MMSI": "555666777", "ShipName": "T", "time_utc": _T1.isoformat()},
                "_fetched_at": _T1.isoformat()}
        msg2["Message"]["PositionReport"]["Latitude"] = 24.81
        msg2["Message"]["PositionReport"]["Longitude"] = 46.68
        ev1 = conn.normalize(msg1)
        ev2 = conn.normalize(msg2)
        segments = conn.build_track_segments([ev1, ev2])
        assert segments, "Expected at least one track segment"
        ref = segments[0].provenance.raw_source_ref
        assert "555666777" in ref
        assert "track" in ref


# ── OpenSky ───────────────────────────────────────────────────────────────────


def _opensky_sv(icao24: str = "abc123", lat: float = 24.8, lon: float = 46.67) -> Dict[str, Any]:
    tp = int(_T0.timestamp())
    sv: List[Any] = [
        icao24,       # 0: icao24
        "SVA001 ",    # 1: callsign
        "Saudi Arabia",  # 2: origin_country
        tp,           # 3: time_position
        tp,           # 4: last_contact
        lon,          # 5: longitude
        lat,          # 6: latitude
        10000.0,      # 7: baro_altitude
        False,        # 8: on_ground
        250.0,        # 9: velocity
        90.0,         # 10: true_track
        0.0,          # 11: vertical_rate
        None,         # 12: sensors
        10000.0,      # 13: geo_altitude
        "1234",       # 14: squawk
        False,        # 15: spi
        0,            # 16: position_source
    ]
    return {"_state": sv, "_fetched_at": _T0.isoformat(), "_bbox": {}}


class TestOpenSkyRawSourceRef:
    def setup_method(self) -> None:
        from src.connectors.opensky import OpenSkyConnector
        self.conn = OpenSkyConnector()

    def test_normalize_sets_entity_specific_ref(self) -> None:
        ev = self.conn.normalize(_opensky_sv(icao24="abc123"))
        ref = ev.provenance.raw_source_ref
        assert ref.startswith("opensky://icao24/abc123@"), f"Unexpected ref: {ref!r}"
        assert "opensky-network.org" not in ref

    def test_ref_contains_icao24(self) -> None:
        ev = self.conn.normalize(_opensky_sv(icao24="def456"))
        assert "def456" in ev.provenance.raw_source_ref

    def test_ref_is_nonempty(self) -> None:
        ev = self.conn.normalize(_opensky_sv())
        assert ev.provenance.raw_source_ref

    def test_different_icao_gives_different_ref(self) -> None:
        ev1 = self.conn.normalize(_opensky_sv(icao24="aaa111"))
        ev2 = self.conn.normalize(_opensky_sv(icao24="bbb222"))
        assert ev1.provenance.raw_source_ref != ev2.provenance.raw_source_ref

    def test_track_segment_ref_contains_icao_and_track(self) -> None:
        sv_t1 = _opensky_sv(icao24="xyz789", lat=24.80, lon=46.67)
        sv_t2 = {
            "_state": list(_opensky_sv(icao24="xyz789", lat=24.82, lon=46.70)["_state"]),
            "_fetched_at": _T1.isoformat(),
            "_bbox": {},
        }
        sv_t2["_state"][3] = int(_T1.timestamp())
        sv_t2["_state"][4] = int(_T1.timestamp())
        ev1 = self.conn.normalize(sv_t1)
        ev2 = self.conn.normalize(sv_t2)
        segments = self.conn.build_track_segments([ev1, ev2])
        assert segments, "Expected at least one track segment"
        ref = segments[0].provenance.raw_source_ref
        assert "xyz789" in ref
        assert "track" in ref


# ── GDELT ─────────────────────────────────────────────────────────────────────


def _gdelt_article(
    url: str = "https://example.com/news/construction-site-riyadh",
    title: str = "New tower rises in Riyadh",
    seendate: str = "20260403T120000Z",
) -> Dict[str, Any]:
    return {
        "url": url,
        "title": title,
        "seendate": seendate,
        "domain": "example.com",
        "language": "English",
        "_aoi_lon": 46.7,
        "_aoi_lat": 24.7,
    }


class TestGdeltRawSourceRef:
    def setup_method(self) -> None:
        from src.connectors.gdelt import GdeltConnector
        self.conn = GdeltConnector()

    def test_normalize_sets_gdelt_doc_ref(self) -> None:
        ev = self.conn.normalize(_gdelt_article())
        ref = ev.provenance.raw_source_ref
        assert ref.startswith("gdelt://doc/"), f"Unexpected ref: {ref!r}"

    def test_ref_is_nonempty(self) -> None:
        ev = self.conn.normalize(_gdelt_article())
        assert ev.provenance.raw_source_ref

    def test_ref_hash_derived_from_url(self) -> None:
        url = "https://example.com/article-abc"
        ev = self.conn.normalize(_gdelt_article(url=url))
        expected_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        assert ev.provenance.raw_source_ref == f"gdelt://doc/{expected_hash}"

    def test_different_urls_give_different_refs(self) -> None:
        ev1 = self.conn.normalize(_gdelt_article(url="https://a.com/story1"))
        ev2 = self.conn.normalize(_gdelt_article(url="https://b.com/story2"))
        assert ev1.provenance.raw_source_ref != ev2.provenance.raw_source_ref

    def test_title_fallback_when_no_url(self) -> None:
        article = _gdelt_article(url="", title="Construction News Headline")
        ev = self.conn.normalize(article)
        ref = ev.provenance.raw_source_ref
        assert ref.startswith("gdelt://doc/")
        expected_hash = hashlib.sha256("Construction News Headline".encode()).hexdigest()[:16]
        assert ev.provenance.raw_source_ref == f"gdelt://doc/{expected_hash}"


# ── STAC (earth-search) ───────────────────────────────────────────────────────


def _stac_item(item_id: str = "S2A_2026_scene_001") -> Dict[str, Any]:
    return {
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[46.0, 24.0], [47.0, 24.0], [47.0, 25.0], [46.0, 25.0], [46.0, 24.0]]],
        },
        "properties": {
            "datetime": "2026-04-01T10:00:00Z",
            "eo:cloud_cover": 5.0,
            "platform": "sentinel-2a",
        },
        "assets": {},
        "links": [],
    }


class TestStacRawSourceRef:
    def test_earth_search_ref_contains_item_id(self) -> None:
        from src.connectors.earth_search import EarthSearchConnector
        conn = EarthSearchConnector()
        ev = conn.normalize(_stac_item("S2A_2026_scene_007"))
        ref = ev.provenance.raw_source_ref
        assert "S2A_2026_scene_007" in ref
        assert ref.startswith("stac://earth-search/")

    def test_stac_ref_is_nonempty(self) -> None:
        from src.connectors.earth_search import EarthSearchConnector
        conn = EarthSearchConnector()
        ev = conn.normalize(_stac_item())
        assert ev.provenance.raw_source_ref

    def test_different_items_give_different_refs(self) -> None:
        from src.connectors.earth_search import EarthSearchConnector
        conn = EarthSearchConnector()
        ev1 = conn.normalize(_stac_item("item-aaa"))
        ev2 = conn.normalize(_stac_item("item-bbb"))
        assert ev1.provenance.raw_source_ref != ev2.provenance.raw_source_ref
