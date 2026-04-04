"""Telemetry event store — ship and aircraft position persistence.

P3-1.6: In-memory store with PostGIS-swap-ready interface for ship/aircraft positions.
P3-4.1: Configurable retention policy (time + count-based pruning).
P3-4.2: Position thinning/downsampling for data older than a configurable threshold.
P3-4.3: Ingest lag statistics (event_time vs ingested_at) for Prometheus exposure.

The ``TelemetryStore`` is intentionally self-contained.  Replacing it with a
PostGIS-backed implementation only requires implementing the same public interface
on a new class — no router or service changes are needed.
"""
from __future__ import annotations

import statistics
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from src.models.canonical_event import CanonicalEvent, EventType


# ── Policy + stats models ──────────────────────────────────────────────────────

# Retention Policy Definitions — Phase 1 Contract
#
# Normalized event retention (EventStore):
#   - In-memory: no automatic pruning; bounded by process lifetime
#   - PostgreSQL (when activated): max_age_days=90 for all event types
#   - Exception: IMAGERY_ACQUISITION scenes kept 365 days
#
# Position telemetry retention (TelemetryStore):
#   - max_age_days=30 (default): discard positions older than 30 days
#   - max_events_per_entity=10000: cap per vessel/aircraft
#   - thin_after_age_days=7: downsample to 5-min intervals for events > 7 days old
#   - These values are frozen for Phase 1; revisit in Phase 6.


class RetentionPolicy(BaseModel):
    """Configurable telemetry retention policy (P3-4.1 + P3-4.2)."""

    max_age_days: int = Field(
        default=30,
        ge=1,
        description="Prune events older than this many days (absolute cutoff).",
    )
    max_events_per_entity: int = Field(
        default=10_000,
        ge=10,
        description="If an entity exceeds this count, keep only the newest N.",
    )
    thin_after_age_days: int = Field(
        default=7,
        ge=1,
        description="Events older than this are subject to downsampling.",
    )
    thin_interval_seconds: int = Field(
        default=300,
        ge=60,
        description=(
            "For events older than thin_after_age_days, keep at most one "
            "position per this interval per entity."
        ),
    )


class IngestLagStats(BaseModel):
    """Ingest lag statistics per telemetry batch (P3-4.3).

    Lag is defined as ``ingested_at - event_time`` in seconds.
    A positive value means the event was received after it occurred (normal).
    Large values (> minutes) indicate data feed latency or backfill.
    """

    median_lag_seconds: float = Field(description="Median lag in seconds.")
    p95_lag_seconds: float = Field(description="95th-percentile lag in seconds.")
    max_lag_seconds: float = Field(description="Maximum observed lag in seconds.")
    sample_count: int = Field(description="Number of events in the lag sample.")


# ── Internal helpers ───────────────────────────────────────────────────────────

# Only position-level event types are tracked in TelemetryStore.
# Track segments are handled by the connectors' build_track_segments() methods.
_POSITION_TYPES: frozenset[str] = frozenset({
    EventType.SHIP_POSITION.value,
    EventType.AIRCRAFT_POSITION.value,
})


def _lon_lat_from_event(event: CanonicalEvent) -> Tuple[Optional[float], Optional[float]]:
    """Extract (lon, lat) from a CanonicalEvent's centroid or geometry.

    Centroid is always a GeoJSON Point — check it first; fall back to geometry.
    """
    return _extract_point_coords(event.centroid) or _extract_point_coords(event.geometry)


def _extract_point_coords(geo: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Return (lon, lat) from a GeoJSON geometry object."""
    gtype = geo.get("type", "")
    coords = geo.get("coordinates", [])
    if gtype == "Point" and len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    if gtype == "Polygon" and coords and coords[0]:
        ring = coords[0]
        # Exclude closing point (duplicate of first point) for accurate centroid
        pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
        if not pts:
            return None, None
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        return lon, lat
    if gtype == "LineString" and coords:
        return float(coords[0][0]), float(coords[0][1])
    return None, None


def _uniform_subsample(events: List[CanonicalEvent], n: int) -> List[CanonicalEvent]:
    """Return n uniformly spaced items from events (first + last always included)."""
    total = len(events)
    if total <= n:
        return events
    if n == 1:
        return [events[0]]
    step = (total - 1) / (n - 1)
    indices = {round(i * step) for i in range(n)}
    indices.add(0)
    indices.add(total - 1)
    return [events[i] for i in sorted(indices)][:n]


# ── Store ──────────────────────────────────────────────────────────────────────


class TelemetryStore:
    """Thread-safe in-memory store for ship and aircraft position events.

    Data model:
      - ``_by_entity`` maps ``entity_id`` → list of CanonicalEvents sorted by event_time ASC.
      - ``_all`` is a flat list used for viewport + lag queries.

    Duplicate events (same ``event_id``) are silently dropped on ingest.
    Only ``EventType.SHIP_POSITION`` and ``EventType.AIRCRAFT_POSITION`` are accepted;
    all other event types are ignored without error.
    """

    def __init__(self) -> None:
        self._by_entity: Dict[str, List[CanonicalEvent]] = {}
        self._all: List[CanonicalEvent] = []
        self._seen_ids: set[str] = set()
        self._lock = threading.Lock()

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def ingest(self, event: CanonicalEvent) -> bool:
        """Upsert a single telemetry event; returns True if accepted.

        Ignores non-position event types and exact duplicate event_ids.
        """
        if event.event_type.value not in _POSITION_TYPES:
            return False
        with self._lock:
            if event.event_id in self._seen_ids:
                return False
            self._seen_ids.add(event.event_id)
            entity_id = event.entity_id or event.event_id
            bucket = self._by_entity.setdefault(entity_id, [])
            bucket.append(event)
            bucket.sort(key=lambda e: e.event_time)
            self._all.append(event)
        return True

    def ingest_batch(self, events: Sequence[CanonicalEvent]) -> int:
        """Ingest multiple events; returns count of accepted (non-duplicate) events."""
        return sum(1 for e in events if self.ingest(e))

    # ── Queries ────────────────────────────────────────────────────────────────

    def query_entity(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        max_points: int = 2_000,
    ) -> List[CanonicalEvent]:
        """Return positions for a single entity within a time window.

        Results are in ascending event_time order.  When the result count
        exceeds max_points, a uniform subsample is returned so that the
        track shape is preserved (first + last points always included).
        """
        with self._lock:
            bucket = list(self._by_entity.get(entity_id, []))
        results = [e for e in bucket if start_time <= e.event_time <= end_time]
        return _uniform_subsample(results, max_points)

    def query_viewport(
        self,
        bbox: Tuple[float, float, float, float],
        start_time: datetime,
        end_time: datetime,
        *,
        sources: Optional[List[str]] = None,
        max_events: int = 2_000,
    ) -> List[CanonicalEvent]:
        """Return position events whose centroid falls inside a viewport bbox.

        ``bbox`` is ``(west, south, east, north)`` in EPSG:4326 decimal degrees.
        Results are sorted newest-first and are hard-capped at ``max_events``.
        This is the server-side viewport-aware query limit (P3-3.5).
        """
        west, south, east, north = bbox
        with self._lock:
            all_events = list(self._all)

        results: List[CanonicalEvent] = []
        for event in all_events:
            if not (start_time <= event.event_time <= end_time):
                continue
            if sources and event.source not in sources:
                continue
            lon, lat = _lon_lat_from_event(event)
            if lon is None:
                continue
            if west <= lon <= east and south <= lat <= north:
                results.append(event)

        results.sort(key=lambda e: e.event_time, reverse=True)
        return results[:max_events]

    def get_entity_ids(
        self,
        *,
        source: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> List[str]:
        """List all tracked entity identifiers, optionally filtered by source or type."""
        with self._lock:
            snapshot = {eid: (lst[0] if lst else None) for eid, lst in self._by_entity.items()}

        return [
            eid
            for eid, first in snapshot.items()
            if first is not None
            and (source is None or first.source == source)
            and (entity_type is None or first.entity_type.value == entity_type)
        ]

    def count(self) -> int:
        """Total number of stored position events."""
        with self._lock:
            return len(self._all)

    # ── Retention enforcement (P3-4.1) ────────────────────────────────────────

    def enforce_retention(self, policy: RetentionPolicy) -> int:
        """Remove events that exceed the retention policy.

        Rule 1 — Age cutoff: delete events older than ``policy.max_age_days``.
        Rule 2 — Count cap: for entities exceeding ``policy.max_events_per_entity``,
                            keep only the newest N (oldest are at the front because
                            events are stored sorted ascending by event_time).

        Returns the total number of pruned events.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=policy.max_age_days)
        pruned = 0

        with self._lock:
            for entity_id in list(self._by_entity.keys()):
                bucket = self._by_entity[entity_id]

                # Rule 1: age cutoff
                before = len(bucket)
                kept = [e for e in bucket if e.event_time >= cutoff]
                pruned += before - len(kept)

                # Rule 2: count cap (oldest events are at the front)
                if len(kept) > policy.max_events_per_entity:
                    excess = len(kept) - policy.max_events_per_entity
                    pruned += excess
                    kept = kept[excess:]

                self._by_entity[entity_id] = kept

            # Rebuild derived structures
            kept_ids: set[str] = set()
            new_all: List[CanonicalEvent] = []
            for bucket in self._by_entity.values():
                for e in bucket:
                    kept_ids.add(e.event_id)
                    new_all.append(e)
            self._all = new_all
            self._seen_ids = kept_ids

        return pruned

    # ── Position thinning (P3-4.2) ────────────────────────────────────────────

    def thin_old_positions(self, policy: RetentionPolicy) -> int:
        """Downsample positions older than ``policy.thin_after_age_days``.

        For each entity, events beyond the thinning threshold are reduced to at
        most one position per ``policy.thin_interval_seconds``.  The most recent
        event in each interval is kept; the rest are discarded.

        Returns the number of thinned events.
        """
        threshold = datetime.now(timezone.utc) - timedelta(days=policy.thin_after_age_days)
        interval = timedelta(seconds=policy.thin_interval_seconds)
        thinned = 0

        with self._lock:
            for entity_id in list(self._by_entity.keys()):
                bucket = self._by_entity[entity_id]
                kept: List[CanonicalEvent] = []
                last_kept_time: Optional[datetime] = None

                for event in bucket:  # sorted ascending
                    if event.event_time >= threshold:
                        # Recent events — always keep, reset thinning boundary
                        kept.append(event)
                        last_kept_time = None
                    else:
                        # Old event — keep if it is the first or far enough from last kept
                        if (
                            last_kept_time is None
                            or (event.event_time - last_kept_time) >= interval
                        ):
                            kept.append(event)
                            last_kept_time = event.event_time
                        else:
                            thinned += 1

                self._by_entity[entity_id] = kept

            # Rebuild flat list + seen_ids
            new_all: List[CanonicalEvent] = []
            new_ids: set[str] = set()
            for bucket in self._by_entity.values():
                for e in bucket:
                    new_all.append(e)
                    new_ids.add(e.event_id)
            self._all = new_all
            self._seen_ids = new_ids

        return thinned

    # ── Ingest lag statistics (P3-4.3) ────────────────────────────────────────

    def get_ingest_lag_stats(self) -> Optional[IngestLagStats]:
        """Compute ingest lag statistics from stored events.

        Lag is measured as ``ingested_at - event_time``.  For new feeds this
        approximates near-real-time latency; for backfilled data it reflects
        how old the events were when they entered the system.

        Returns ``None`` when the store is empty.
        """
        with self._lock:
            events = list(self._all)

        if not events:
            return None

        lags: List[float] = []
        for e in events:
            lag = (e.ingested_at - e.event_time).total_seconds()
            if lag >= 0:
                lags.append(lag)

        if not lags:
            return None

        lags_sorted = sorted(lags)
        n = len(lags_sorted)
        median = statistics.median(lags_sorted)
        p95 = lags_sorted[min(int(n * 0.95), n - 1)]

        return IngestLagStats(
            median_lag_seconds=round(median, 3),
            p95_lag_seconds=round(p95, 3),
            max_lag_seconds=round(lags_sorted[-1], 3),
            sample_count=n,
        )


# Module-level singleton — used by pollers and app alike.
# Cross-process sharing requires PostgreSQL activation (see docs/ARCHITECTURE.md).
_default_store: "TelemetryStore | None" = None


def get_default_telemetry_store() -> "TelemetryStore":
    """Return the process-wide TelemetryStore singleton.

    In single-process mode (tests, dev) this provides a shared in-memory store.
    In production the store is backed by PostgreSQL once DATABASE_URL is set;
    cross-process sharing then happens transparently through the DB layer.
    """
    global _default_store
    if _default_store is None:
        _default_store = TelemetryStore()
    return _default_store
