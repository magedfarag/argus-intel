"""Strike / battle-damage reconstruction connector — stub implementation for
Phase 2, Track D.

Generates deterministic synthetic strike events for replay-safe testing and API
seeding.  Attribution follows ACLED (Association for Conflict and Location Data,
acleddata.com) conventions.  No external HTTP calls are made.

connector_id: strike-reconstruction-stub
source_type:  derived
provenance:   acled-stub
"""
from __future__ import annotations

import hashlib
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
from src.models.operational_layers import EvidenceLink, StrikeEvent


# ── Synthetic strike seed data ─────────────────────────────────────────────────
# (region_slug, centre_lon, centre_lat, target_description)
_STRIKE_SPECS: List[tuple[str, float, float, str]] = [
    ("eastern-ukraine-donetsk",    37.80, 47.90, "industrial infrastructure"),
    ("eastern-ukraine-zaporizhzhia", 35.20, 47.50, "energy facility"),
    ("kharkiv-region",             36.30, 49.90, "residential area"),
    ("southern-ukraine-kherson",   32.60, 46.70, "logistics hub"),
    ("crimea-sevastopol",          33.50, 44.60, "naval installation"),
    ("dnipro-city",                35.00, 48.50, "civilian infrastructure"),
]

_STRIKE_TYPES: List[str] = ["airstrike", "artillery", "missile", "drone"]
_DAMAGE_SEVERITIES: List[str] = ["minor", "moderate", "severe", "destroyed"]

_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="check-provider-terms",
    redistribution="check-provider-terms",
    attribution_required=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _seed_from_window(start_time: datetime, end_time: datetime) -> int:
    """Derive a deterministic integer seed from a time window."""
    raw = f"strikes:{start_time.isoformat()}|{end_time.isoformat()}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)


def _make_evidence_uuid(seed: int, idx: int) -> str:
    """Generate a deterministic evidence ID from a seed and index."""
    raw = f"evidence:{seed}:{idx}"
    return "ev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


# ── Connector ─────────────────────────────────────────────────────────────────


class StrikeConnector(BaseConnector):
    """Stub connector for strike event ingestion and reconstruction.

    Implements the full BaseConnector interface.  All data is synthetic and
    deterministic (seeded from the query window) — safe for replay testing.
    No external HTTP calls are made.
    """

    connector_id: str = "strike-reconstruction-stub"
    display_name: str = "Strike Reconstruction (stub)"
    source_type: str = "derived"

    _SOURCE: str = "strike-reconstruction-stub"
    _PROVENANCE: str = "acled-stub"

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
        """Delegate to fetch_strikes and return raw dicts."""
        events = self.fetch_strikes(start_time, end_time)
        return [e.model_dump(mode="json") for e in events]

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Convert a single raw strike dict to a CanonicalEvent.

        Raises:
            NormalizationError: if the raw record cannot be parsed.
        """
        try:
            event = StrikeEvent(**raw)
        except Exception as exc:
            raise NormalizationError(f"Cannot normalise strike record: {exc}") from exc
        return self.to_canonical_events([event])[0]

    def health(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=True,
            message="Stub connector — no remote dependency",
            last_successful_poll=datetime.now(timezone.utc),
        )

    # ── Domain methods ────────────────────────────────────────────────────

    def fetch_strikes(
        self,
        start_time: datetime,
        end_time: datetime,
        region_bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> List[StrikeEvent]:
        """Generate 4–6 deterministic synthetic strike events for the window.

        The output is reproducible: the same (start_time, end_time) always
        yields the same events, enabling replay-safe testing.

        Args:
            start_time:  Query window start (UTC-aware).
            end_time:    Query window end   (UTC-aware).
            region_bbox: Optional (min_lon, min_lat, max_lon, max_lat) filter
                         applied after generation.

        Returns:
            List of StrikeEvent instances ordered by occurred_at ascending.
        """
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        seed = _seed_from_window(start_time, end_time)
        rng = random.Random(seed)
        specs = list(_STRIKE_SPECS)
        rng.shuffle(specs)
        count = rng.randint(4, 6)
        selected = specs[:count]

        span_seconds = max(int((end_time - start_time).total_seconds()), 1)
        events: List[StrikeEvent] = []

        for i, (region, lon, lat, target_desc) in enumerate(selected):
            offset_seconds = rng.randint(0, span_seconds - 1)
            occurred_at = start_time + timedelta(seconds=offset_seconds)

            strike_type = rng.choice(_STRIKE_TYPES)
            damage_severity = rng.choice(_DAMAGE_SEVERITIES)
            confidence = round(rng.uniform(0.5, 0.9), 3)
            corroboration = rng.randint(1, 3)

            event_lon = round(lon + rng.uniform(-0.05, 0.05), 5)
            event_lat = round(lat + rng.uniform(-0.05, 0.05), 5)

            strike_id = make_event_id(self._SOURCE, region, occurred_at)

            n_evidence = rng.randint(1, 2)
            evidence_refs = [
                _make_evidence_uuid(seed, i * 10 + j) for j in range(n_evidence)
            ]

            events.append(
                StrikeEvent(
                    strike_id=strike_id,
                    occurred_at=occurred_at,
                    location_lon=event_lon,
                    location_lat=event_lat,
                    location_geojson={
                        "type": "Point",
                        "coordinates": [event_lon, event_lat],
                    },
                    strike_type=strike_type,
                    target_description=target_desc,
                    damage_severity=damage_severity,
                    confidence=confidence,
                    evidence_refs=evidence_refs,
                    source=self._SOURCE,
                    provenance=self._PROVENANCE,
                    corroboration_count=corroboration,
                )
            )

        if region_bbox is not None:
            min_lon, min_lat, max_lon, max_lat = region_bbox
            events = [
                e for e in events
                if min_lon <= e.location_lon <= max_lon
                and min_lat <= e.location_lat <= max_lat
            ]

        events.sort(key=lambda e: e.occurred_at)
        return events

    def add_evidence(
        self,
        event: StrikeEvent,
        links: List[EvidenceLink],
    ) -> StrikeEvent:
        """Append evidence links to a StrikeEvent and update corroboration_count.

        Only evidence IDs not already present in ``event.evidence_refs`` are
        added.  Returns a new StrikeEvent instance (Pydantic model_copy
        semantics — original is unchanged).

        Args:
            event: The StrikeEvent to update.
            links: EvidenceLink instances whose evidence_ids will be appended.

        Returns:
            A new StrikeEvent with updated evidence_refs and corroboration_count.
        """
        new_refs = list(event.evidence_refs)
        added = 0
        for link in links:
            if link.evidence_id not in new_refs:
                new_refs.append(link.evidence_id)
                added += 1

        return event.model_copy(
            update={
                "evidence_refs": new_refs,
                "corroboration_count": event.corroboration_count + added,
            }
        )

    def to_canonical_events(
        self, events: List[StrikeEvent]
    ) -> List[CanonicalEvent]:
        """Convert StrikeEvent instances to CanonicalEvents for EventStore ingestion.

        Uses location_geojson as the canonical geometry when available;
        falls back to a GeoJSON Point at (location_lon, location_lat).
        """
        canonical: List[CanonicalEvent] = []
        for ev in events:
            geometry: Dict[str, Any] = ev.location_geojson or {
                "type": "Point",
                "coordinates": [ev.location_lon, ev.location_lat],
            }
            centroid: Dict[str, Any] = {
                "type": "Point",
                "coordinates": [ev.location_lon, ev.location_lat],
            }
            canonical.append(
                CanonicalEvent(
                    event_id=ev.strike_id,
                    source=ev.source,
                    source_type=SourceType.DERIVED,
                    entity_type=EntityType.SYSTEM,
                    entity_id=ev.strike_id,
                    event_type=EventType.STRIKE_EVENT,
                    event_time=ev.occurred_at,
                    geometry=geometry,
                    centroid=centroid,
                    confidence=ev.confidence,
                    attributes={
                        "strike_type": ev.strike_type,
                        "target_description": ev.target_description,
                        "damage_severity": ev.damage_severity,
                        "corroboration_count": ev.corroboration_count,
                        "evidence_refs": ev.evidence_refs,
                    },
                    normalization=NormalizationRecord(
                        normalized_by=f"connector.{self.connector_id}"
                    ),
                    provenance=ProvenanceRecord(raw_source_ref=ev.provenance),
                    license=_LICENSE,
                )
            )
        return canonical
