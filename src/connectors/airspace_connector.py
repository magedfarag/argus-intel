"""Airspace restriction and NOTAM stub connector — Track B, Phase 2.

Implements FAA-style airspace restriction and NOTAM ingestion for demo
environments.  No HTTP calls are made; all data is seeded deterministically.

connector_id: ``faa-notam-stub``
source_type:  ``context_feed``

Design notes:
- Stub returns 4 representative airspace restrictions covering common types:
  TFR (Temporary Flight Restriction), MOA (Military Operations Area),
  NFZ (No-Fly Zone), and ADIZ (Air Defence Identification Zone).
- Stub NOTAM set contains 3 representative notices for demo ICAO codes.
- ``is_active()`` compares UTC now against ``valid_from`` / ``valid_to``.
- All datetime fields are UTC-aware (timezone.utc).
- Canonical-event conversion helpers are provided as free functions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    NormalizationError,
)
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
from src.models.operational_layers import AirspaceRestriction, NotamEvent

logger = logging.getLogger(__name__)

_SOURCE = "faa_notam_stub"

# FAA NOTAM data is public, but redistribution terms vary; mark conservative.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)

# ────────────────────────────────────────────────────────────────────────────
# Stub seed data
# ────────────────────────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc)

# Stub restrictions — geographically representative sample
_STUB_RESTRICTIONS: List[AirspaceRestriction] = [
    AirspaceRestriction(
        restriction_id="TFR-2026-0001",
        name="WASHINGTON DC SFRA TFR",
        restriction_type="TFR",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-77.5, 38.5], [-76.8, 38.5], [-76.8, 39.1],
                [-77.5, 39.1], [-77.5, 38.5],
            ]],
        },
        lower_limit_ft=0.0,
        upper_limit_ft=18000.0,
        valid_from=_NOW - timedelta(days=30),
        valid_to=_NOW + timedelta(days=60),
        is_active=True,
        source=_SOURCE,
        provenance="https://tfr.faa.gov/tfr2/list.jsp#TFR-2026-0001",
    ),
    AirspaceRestriction(
        restriction_id="MOA-NELLIS-01",
        name="NELLIS MOA SECTOR 4",
        restriction_type="MOA",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-116.0, 36.5], [-114.5, 36.5], [-114.5, 37.8],
                [-116.0, 37.8], [-116.0, 36.5],
            ]],
        },
        lower_limit_ft=500.0,
        upper_limit_ft=60000.0,
        valid_from=_NOW - timedelta(days=180),
        valid_to=_NOW + timedelta(days=185),
        is_active=True,
        source=_SOURCE,
        provenance="https://www.faa.gov/air_traffic/special_use/MOA/NELLIS-4",
    ),
    AirspaceRestriction(
        restriction_id="NFZ-PENTAGON-2026",
        name="PENTAGON NFZ",
        restriction_type="NFZ",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-77.075, 38.865], [-77.045, 38.865], [-77.045, 38.895],
                [-77.075, 38.895], [-77.075, 38.865],
            ]],
        },
        lower_limit_ft=0.0,
        upper_limit_ft=99999.0,
        valid_from=_NOW - timedelta(days=365),
        valid_to=None,  # indefinite
        is_active=True,
        source=_SOURCE,
        provenance="https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/nfz",
    ),
    AirspaceRestriction(
        restriction_id="TFR-2026-EXPIRED",
        name="SUPERSEDED EXERCISE TFR",
        restriction_type="TFR",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-100.0, 35.0], [-99.0, 35.0], [-99.0, 36.0],
                [-100.0, 36.0], [-100.0, 35.0],
            ]],
        },
        lower_limit_ft=0.0,
        upper_limit_ft=10000.0,
        valid_from=_NOW - timedelta(days=10),
        valid_to=_NOW - timedelta(days=2),  # already expired
        is_active=False,
        source=_SOURCE,
        provenance="https://tfr.faa.gov/tfr2/list.jsp#TFR-2026-EXPIRED",
    ),
    AirspaceRestriction(
        restriction_id="ADIZ-EASTERN-SEABOARD",
        name="US EASTERN ADIZ",
        restriction_type="ADIZ",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-75.0, 37.0], [-71.0, 37.0], [-71.0, 41.0],
                [-75.0, 41.0], [-75.0, 37.0],
            ]],
        },
        lower_limit_ft=0.0,
        upper_limit_ft=60000.0,
        valid_from=_NOW - timedelta(days=365 * 5),
        valid_to=None,  # permanent
        is_active=True,
        source=_SOURCE,
        provenance="https://www.faa.gov/air_traffic/publications/ADIZ",
    ),
]

# Stub NOTAMs — 3 representative notices
_STUB_NOTAMS: List[NotamEvent] = [
    NotamEvent(
        notam_id="notam-001",
        notam_number="A0123/26",
        subject="Runway closed for maintenance",
        condition="RWY 27L/09R CLSD DUE CONSTRUCTION WIP",
        location_icao="KDCA",
        effective_from=_NOW - timedelta(days=3),
        effective_to=_NOW + timedelta(days=14),
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-77.041, 38.849], [-77.040, 38.849],
                [-77.040, 38.850], [-77.041, 38.850],
                [-77.041, 38.849],
            ]],
        },
        raw_text="A0123/26 NOTAMN\nQ) ZDC/QMRLC/IV/NBO/A/000/001/3851N07704W001\nA) KDCA B) 2604011200 C) 2604150600\nE) RWY 27L/09R CLSD DUE CONSTRUCTION WIP\nCREATED: 01 Apr 2026 10:00:00",
        source=_SOURCE,
    ),
    NotamEvent(
        notam_id="notam-002",
        notam_number="A0456/26",
        subject="Airspace restricted - UAS exercise",
        condition="UAS EXERCISE AREA ACT. ALTITUDE: SFC TO 400FT AGL",
        location_icao="KJFK",
        effective_from=_NOW,
        effective_to=_NOW + timedelta(hours=6),
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[
                [-73.82, 40.60], [-73.75, 40.60], [-73.75, 40.66],
                [-73.82, 40.66], [-73.82, 40.60],
            ]],
        },
        raw_text="A0456/26 NOTAMN\nQ) ZNY/QRTCA/IV/BO/W/000/001/4038N07348W002\nB) 2604040000 C) 2604040600\nE) UAS EXERCISE AREA ACT. ALTITUDE: SFC TO 400FT AGL\nCREATED: 04 Apr 2026 00:00:00",
        source=_SOURCE,
    ),
    NotamEvent(
        notam_id="notam-003",
        notam_number="A0789/26",
        subject="Navigation aid out of service",
        condition="VOR/DME OKITE OUT OF SERVICE",
        location_icao="KLAX",
        effective_from=_NOW - timedelta(days=1),
        effective_to=_NOW + timedelta(days=30),
        geometry_geojson=None,
        raw_text="A0789/26 NOTAMN\nQ) ZLA/QNAVX/I//, /A/000/999/3356N11825W025\nB) 2604030000 C) 2605032359\nE) VOR/DME OKITE OUT OF SERVICE\nCREATED: 03 Apr 2026 00:00:00",
        source=_SOURCE,
    ),
]


# ────────────────────────────────────────────────────────────────────────────
# Canonical-event conversion helpers
# ────────────────────────────────────────────────────────────────────────────

def restriction_to_canonical_event(r: AirspaceRestriction) -> CanonicalEvent:
    """Convert an ``AirspaceRestriction`` to a ``CanonicalEvent`` for ingest."""
    geojson = r.geometry_geojson
    coords = geojson.get("coordinates", [[]])[0]
    if coords:
        avg_lon = sum(c[0] for c in coords) / len(coords)
        avg_lat = sum(c[1] for c in coords) / len(coords)
        centroid: Dict[str, Any] = {"type": "Point", "coordinates": [round(avg_lon, 4), round(avg_lat, 4)]}
    else:
        centroid = {"type": "Point", "coordinates": [0.0, 0.0]}

    event_id = make_event_id(_SOURCE, r.restriction_id, r.valid_from)

    return CanonicalEvent(
        event_id=event_id,
        source=_SOURCE,
        source_type=SourceType.CONTEXT_FEED,
        entity_type=EntityType.SYSTEM,
        entity_id=r.restriction_id,
        event_type=EventType.AIRSPACE_RESTRICTION,
        event_time=r.valid_from,
        time_start=r.valid_from,
        time_end=r.valid_to,
        geometry=geojson,
        centroid=centroid,
        confidence=1.0,
        attributes={
            "restriction_id": r.restriction_id,
            "name": r.name,
            "restriction_type": r.restriction_type,
            "lower_limit_ft": r.lower_limit_ft,
            "upper_limit_ft": r.upper_limit_ft,
            "is_active": r.is_active,
        },
        normalization=NormalizationRecord(
            normalized_by="connector.airspace.notam_stub",
        ),
        provenance=ProvenanceRecord(
            raw_source_ref=r.provenance or f"notam_stub://{r.restriction_id}",
            source_record_id=r.restriction_id,
        ),
        license=_LICENSE,
    )


def notam_to_canonical_event(n: NotamEvent) -> CanonicalEvent:
    """Convert a ``NotamEvent`` to a ``CanonicalEvent`` for ingest."""
    if n.geometry_geojson:
        geometry: Dict[str, Any] = n.geometry_geojson
        coords = geometry.get("coordinates", [[]])[0]
        if coords:
            avg_lon = sum(c[0] for c in coords) / len(coords)
            avg_lat = sum(c[1] for c in coords) / len(coords)
            centroid: Dict[str, Any] = {"type": "Point", "coordinates": [round(avg_lon, 4), round(avg_lat, 4)]}
        else:
            centroid = {"type": "Point", "coordinates": [0.0, 0.0]}
    else:
        geometry = {"type": "Point", "coordinates": [0.0, 0.0]}
        centroid = {"type": "Point", "coordinates": [0.0, 0.0]}

    event_id = make_event_id(_SOURCE, n.notam_id, n.effective_from)

    return CanonicalEvent(
        event_id=event_id,
        source=_SOURCE,
        source_type=SourceType.CONTEXT_FEED,
        entity_type=EntityType.SYSTEM,
        entity_id=n.notam_id,
        event_type=EventType.NOTAM_EVENT,
        event_time=n.effective_from,
        time_start=n.effective_from,
        time_end=n.effective_to,
        geometry=geometry,
        centroid=centroid,
        confidence=1.0,
        attributes={
            "notam_id": n.notam_id,
            "notam_number": n.notam_number,
            "subject": n.subject,
            "condition": n.condition,
            "location_icao": n.location_icao,
        },
        normalization=NormalizationRecord(
            normalized_by="connector.airspace.notam_stub",
        ),
        provenance=ProvenanceRecord(
            raw_source_ref=f"notam_stub://{n.notam_id}",
            source_record_id=n.notam_id,
        ),
        license=_LICENSE,
    )


# ────────────────────────────────────────────────────────────────────────────
# AirspaceConnector
# ────────────────────────────────────────────────────────────────────────────

class AirspaceConnector(BaseConnector):
    """Stub connector for FAA airspace restrictions and NOTAMs.

    Returns deterministic synthetic data seeded at module load time.
    No network calls are made.
    """

    connector_id: str = "faa-notam-stub"
    display_name: str = "FAA NOTAM Stub"
    source_type: str = "context_feed"

    def __init__(self) -> None:
        self._connected: bool = False

    # ── BaseConnector abstract methods ────────────────────────────────────

    def connect(self) -> None:
        """No remote endpoint; mark as connected immediately."""
        self._connected = True
        logger.info("AirspaceConnector: stub connected (no remote endpoint).")

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Return all stub restrictions and NOTAMs as raw dicts."""
        results: List[Dict[str, Any]] = []
        for r in _STUB_RESTRICTIONS:
            results.append({"_type": "restriction", **r.model_dump(mode="json")})
        for n in _STUB_NOTAMS:
            results.append({"_type": "notam", **n.model_dump(mode="json")})
        return results

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Normalize a raw restriction or NOTAM dict into a CanonicalEvent.

        ``raw`` must contain a ``_type`` key of ``'restriction'`` or ``'notam'``.
        """
        record_type = raw.get("_type")
        try:
            if record_type == "restriction":
                r = AirspaceRestriction.model_validate(
                    {k: v for k, v in raw.items() if k != "_type"}
                )
                return restriction_to_canonical_event(r)
            elif record_type == "notam":
                n = NotamEvent.model_validate(
                    {k: v for k, v in raw.items() if k != "_type"}
                )
                return notam_to_canonical_event(n)
            else:
                raise NormalizationError(f"Unknown record type: {record_type!r}")
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(f"Cannot normalize airspace record: {exc}") from exc

    def health(self) -> ConnectorHealthStatus:
        """Return health snapshot — always healthy for stub."""
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=True,
            message="Stub connector — always healthy",
            last_successful_poll=datetime.now(timezone.utc),
            error_count=0,
        )

    # ── Airspace-specific public API ──────────────────────────────────────

    def fetch_restrictions(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[AirspaceRestriction]:
        """Return stub airspace restrictions, optionally filtered by bounding box.

        Args:
            bbox: Optional ``(min_lon, min_lat, max_lon, max_lat)`` tuple.
                  When provided, only restrictions whose polygon centroid falls
                  within the bbox are returned.

        Returns:
            List of ``AirspaceRestriction`` objects.
        """
        restrictions = list(_STUB_RESTRICTIONS)
        if bbox is None:
            return restrictions

        min_lon, min_lat, max_lon, max_lat = bbox
        filtered: List[AirspaceRestriction] = []
        for r in restrictions:
            coords = r.geometry_geojson.get("coordinates", [[]])[0]
            if not coords:
                continue
            clon = sum(c[0] for c in coords) / len(coords)
            clat = sum(c[1] for c in coords) / len(coords)
            if min_lon <= clon <= max_lon and min_lat <= clat <= max_lat:
                filtered.append(r)
        return filtered

    def fetch_notams(self, icao_code: Optional[str] = None) -> List[NotamEvent]:
        """Return stub NOTAMs, optionally filtered by ICAO location code.

        Args:
            icao_code: ICAO 4-letter location indicator (e.g. ``'KDCA'``).
                       When provided, only NOTAMs matching the code are returned.
                       Case-insensitive comparison.

        Returns:
            List of ``NotamEvent`` objects.
        """
        notams = list(_STUB_NOTAMS)
        if icao_code is None:
            return notams
        upper = icao_code.upper()
        return [n for n in notams if n.location_icao and n.location_icao.upper() == upper]

    @staticmethod
    def is_active(restriction: AirspaceRestriction) -> bool:
        """Return True if the restriction is currently active.

        Compares UTC now against ``valid_from`` / ``valid_to``.
        A restriction with ``valid_to=None`` is treated as indefinite (active
        if already past its start).
        """
        now = datetime.now(timezone.utc)
        if restriction.valid_from > now:
            return False
        if restriction.valid_to is not None and restriction.valid_to <= now:
            return False
        return True
