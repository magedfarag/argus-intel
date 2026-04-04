"""GPS / GNSS Jamming connector — stub implementation for Phase 2, Track C.

Generates deterministic synthetic jamming events for known conflict zones
(eastern Mediterranean, Black Sea, Baltic) for replay-safe testing and API
seeding.  No external HTTP calls are made.

connector_id: gnss-monitor-derived
source_type:  derived
provenance:   gps-jammer-tracker-stub
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    NormalizationError,
)
from src.models.canonical_event import (
    CanonicalEvent,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.models.operational_layers import GpsJammingEvent


# ── Known conflict-zone jamming centres ───────────────────────────────────────
# (zone_slug, centre_lon, centre_lat, nominal_radius_km, jamming_type)
_ZONE_SPECS: List[tuple[str, float, float, float, str]] = [
    ("east-med-cyprus",       33.60,  35.10, 120.0, "spoofing"),
    ("black-sea-crimea",      33.40,  44.90, 180.0, "jamming"),
    ("black-sea-odessa",      31.60,  46.50,  90.0, "interference"),
    ("baltic-kaliningrad",    20.50,  54.70, 150.0, "jamming"),
    ("baltic-finland-gulf",   25.00,  60.30,  80.0, "interference"),
]

_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)


# ── Geometry helpers ──────────────────────────────────────────────────────────


def _circle_polygon_geojson(
    lon: float,
    lat: float,
    radius_km: float,
    steps: int = 16,
) -> Dict[str, Any]:
    """Return a closed GeoJSON Polygon approximating a circle (flat-earth).

    Points are evenly distributed around the circumference.  The ring is
    closed (first == last point) as required by RFC 7946.
    """
    # 1 degree latitude ≈ 111.32 km; longitude shrinks with cos(lat)
    d_lat = radius_km / 111.32
    d_lon = radius_km / (111.32 * math.cos(math.radians(lat)))

    coords: List[List[float]] = []
    for i in range(steps):
        angle = 2.0 * math.pi * i / steps
        coords.append([
            round(lon + d_lon * math.cos(angle), 6),
            round(lat + d_lat * math.sin(angle), 6),
        ])
    coords.append(coords[0])  # close ring

    return {"type": "Polygon", "coordinates": [coords]}


def _seed_from_window(start_time: datetime, end_time: datetime) -> int:
    """Derive a deterministic integer seed from a time window."""
    raw = f"jamming:{start_time.isoformat()}|{end_time.isoformat()}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)


# ── Connector ─────────────────────────────────────────────────────────────────


class JammingConnector(BaseConnector):
    """Stub connector for GPS/GNSS jamming event detection.

    Implements the full BaseConnector interface.  All data is synthetic and
    deterministic (seeded from the query window) — safe for replay testing.
    No external HTTP calls are made.
    """

    connector_id: str = "gnss-monitor-derived"
    display_name: str = "GNSS Jamming Monitor (stub)"
    source_type: str = "derived"

    _SOURCE: str = "gnss-monitor-derived"
    _PROVENANCE: str = "gps-jammer-tracker-stub"

    # ── BaseConnector mandatory interface ─────────────────────────────────

    def connect(self) -> None:
        """No external connection required for stub."""

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Delegate to detect_jamming_events and return raw dicts."""
        events = self.detect_jamming_events(start_time, end_time)
        return [e.model_dump(mode="json") for e in events]

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Convert a single raw jamming dict to a CanonicalEvent.

        Raises:
            NormalizationError: if the raw record cannot be parsed.
        """
        try:
            event = GpsJammingEvent(**raw)
        except Exception as exc:
            raise NormalizationError(f"Cannot normalise jamming record: {exc}") from exc
        return self.to_canonical_events([event])[0]

    def health(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=True,
            message="Stub connector — no remote dependency",
            last_successful_poll=datetime.now(timezone.utc),
        )

    # ── Domain methods ────────────────────────────────────────────────────

    def detect_jamming_events(
        self,
        start_time: datetime,
        end_time: datetime,
        region_bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> List[GpsJammingEvent]:
        """Generate 3–5 deterministic synthetic jamming events for the window.

        The output is reproducible: the same (start_time, end_time) always
        yields the same events, enabling replay-safe testing.

        Args:
            start_time:  Query window start (UTC-aware).
            end_time:    Query window end   (UTC-aware).
            region_bbox: Optional (min_lon, min_lat, max_lon, max_lat) filter
                         applied after generation.

        Returns:
            List of GpsJammingEvent instances ordered by detected_at ascending.
        """
        # Ensure timezone-aware input
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        rng = random.Random(_seed_from_window(start_time, end_time))
        zones = list(_ZONE_SPECS)
        rng.shuffle(zones)
        count = rng.randint(3, 5)
        selected_zones = zones[:count]

        span_seconds = max(int((end_time - start_time).total_seconds()), 1)
        events: List[GpsJammingEvent] = []

        for i, (zone_name, lon, lat, radius_km, jamming_type) in enumerate(selected_zones):
            offset_seconds = rng.randint(0, span_seconds - 1)
            detected_at = start_time + timedelta(seconds=offset_seconds)

            # Jitter centre slightly for realism while remaining deterministic
            event_lon = round(lon + rng.uniform(-0.3, 0.3), 5)
            event_lat = round(lat + rng.uniform(-0.2, 0.2), 5)
            event_radius = round(radius_km * rng.uniform(0.8, 1.2), 1)
            confidence = round(rng.uniform(0.6, 0.85), 3)

            jamming_id = make_event_id(self._SOURCE, zone_name, detected_at)
            geo = _circle_polygon_geojson(event_lon, event_lat, event_radius)

            events.append(
                GpsJammingEvent(
                    jamming_id=jamming_id,
                    detected_at=detected_at,
                    location_lon=event_lon,
                    location_lat=event_lat,
                    radius_km=event_radius,
                    affected_area_geojson=geo,
                    jamming_type=jamming_type,
                    confidence=confidence,
                    source=self._SOURCE,
                    provenance=self._PROVENANCE,
                    detection_method="derived",
                )
            )

        if region_bbox is not None:
            min_lon, min_lat, max_lon, max_lat = region_bbox
            events = [
                e for e in events
                if min_lon <= e.location_lon <= max_lon
                and min_lat <= e.location_lat <= max_lat
            ]

        events.sort(key=lambda e: e.detected_at)
        return events

    def to_canonical_events(
        self, events: List[GpsJammingEvent]
    ) -> List[CanonicalEvent]:
        """Convert GpsJammingEvent instances to CanonicalEvents for EventStore ingestion.

        Uses the affected_area_geojson Polygon as the canonical geometry when
        available; falls back to a GeoJSON Point at (location_lon, location_lat).
        """
        canonical: List[CanonicalEvent] = []
        for ev in events:
            geometry: Dict[str, Any] = ev.affected_area_geojson or {
                "type": "Point",
                "coordinates": [ev.location_lon, ev.location_lat],
            }
            centroid: Dict[str, Any] = {
                "type": "Point",
                "coordinates": [ev.location_lon, ev.location_lat],
            }
            canonical.append(
                CanonicalEvent(
                    event_id=ev.jamming_id,
                    source=ev.source,
                    source_type=SourceType.DERIVED,
                    entity_type=EntityType.SYSTEM,
                    entity_id=ev.jamming_id,
                    event_type=EventType.GPS_JAMMING_EVENT,
                    event_time=ev.detected_at,
                    geometry=geometry,
                    centroid=centroid,
                    confidence=ev.confidence,
                    attributes={
                        "jamming_type": ev.jamming_type,
                        "radius_km": ev.radius_km,
                        "detection_method": ev.detection_method,
                        "signal_strength_db": ev.signal_strength_db,
                    },
                    normalization=NormalizationRecord(
                        normalized_by=f"connector.{self.connector_id}"
                    ),
                    provenance=ProvenanceRecord(raw_source_ref=ev.provenance),
                    license=_LICENSE,
                )
            )
        return canonical
