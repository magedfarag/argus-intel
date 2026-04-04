"""Evidence pack service — Phase 5 Track B.

Assembles EvidencePack instances from canonical events, investigations,
or explicit event ID lists. Renders packs to JSON, Markdown, or GeoJSON bytes.

Thread-safe in-memory store; follows the same singleton pattern as
src/services/investigation_service.py.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from src.models.evidence_pack import (
    EvidencePack,
    EvidencePackFormat,
    EvidencePackRequest,
    EvidencePackSection,
    LayerSummaryEntry,
    ProvenanceRecord,
    TimelineEntry,
)
from src.models.canonical_event import CanonicalEvent
from src.services.event_store import get_default_event_store
from src.services.investigation_service import get_default_investigation_store


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _event_to_timeline_entry(event: CanonicalEvent) -> TimelineEntry:
    """Convert a CanonicalEvent to a TimelineEntry."""
    summary_parts: List[str] = []
    if event.attributes:
        if "headline" in event.attributes and event.attributes["headline"]:
            summary_parts.append(str(event.attributes["headline"]))
        elif "vessel_name" in event.attributes and event.attributes["vessel_name"]:
            summary_parts.append(str(event.attributes["vessel_name"]))
        elif "callsign" in event.attributes and event.attributes["callsign"]:
            summary_parts.append(str(event.attributes["callsign"]))
    summary = summary_parts[0] if summary_parts else f"{event.event_type.value} from {event.source}"
    return TimelineEntry(
        timestamp=event.event_time,
        event_type=event.event_type.value,
        event_id=event.event_id,
        summary=summary,
        source=event.source,
        confidence=event.confidence,
        layer=event.event_type.value,
    )


def _build_layer_summaries(events: List[CanonicalEvent]) -> List[LayerSummaryEntry]:
    """Group events by event_type and produce a LayerSummaryEntry per group."""
    groups: Dict[str, List[CanonicalEvent]] = {}
    for e in events:
        key = e.event_type.value
        groups.setdefault(key, []).append(e)

    summaries: List[LayerSummaryEntry] = []
    for layer_name, layer_events in sorted(groups.items()):
        times = [e.event_time for e in layer_events]
        sources = sorted({e.source for e in layer_events})
        summaries.append(
            LayerSummaryEntry(
                layer_name=layer_name,
                event_count=len(layer_events),
                time_range_start=min(times) if times else None,
                time_range_end=max(times) if times else None,
                coverage_description=f"{len(layer_events)} event(s) across {len(sources)} source(s)",
                sources=sources,
            )
        )
    return summaries


def _build_provenance_records(events: List[CanonicalEvent]) -> List[ProvenanceRecord]:
    """Extract unique (source, source_type) pairs and count their events."""
    groups: Dict[str, Dict] = {}
    for e in events:
        key = f"{e.source}::{e.source_type.value}"
        if key not in groups:
            groups[key] = {
                "source_name": e.source,
                "source_type": e.source_type.value,
                "event_count": 0,
                "license": e.license.redistribution if e.license else None,
            }
        groups[key]["event_count"] += 1

    return [
        ProvenanceRecord(
            source_name=v["source_name"],
            source_type=v["source_type"],
            event_count=v["event_count"],
            license=v["license"],
            retrieval_timestamp=datetime.now(timezone.utc),
        )
        for v in sorted(groups.values(), key=lambda x: x["source_name"])
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────


class EvidencePackService:
    """Thread-safe in-memory store and generator for EvidencePack instances."""

    def __init__(self) -> None:
        self._packs: Dict[str, EvidencePack] = {}
        self._lock = threading.Lock()

    # ── Generation ────────────────────────────────────────────────────────────

    def generate_pack(self, req: EvidencePackRequest) -> EvidencePack:
        """Assemble an evidence pack and persist it.

        Resolution order for events:
          1. ``req.event_ids`` — explicit list
          2. ``req.investigation_id`` — pull linked_event_ids from investigation
          3. ``req.time_window_start`` / ``req.time_window_end`` — time-slice the event store
          4. fallback: empty list
        """
        event_store = get_default_event_store()

        # Resolve the event pool
        resolved_ids: Optional[List[str]] = None
        inv_evidence_links: List[dict] = []
        inv_notes: List[str] = []

        if req.event_ids is not None:
            resolved_ids = list(req.event_ids)
        elif req.investigation_id is not None:
            inv_store = get_default_investigation_store()
            inv = inv_store.get(req.investigation_id)
            if inv is not None:
                resolved_ids = list(inv.linked_event_ids)
                inv_evidence_links = [el.model_dump() for el in inv.evidence_links]
                inv_notes = [n.content for n in inv.notes]

        # Fetch canonical events
        events: List[CanonicalEvent] = []
        if resolved_ids is not None:
            for eid in resolved_ids:
                ev = event_store.get(eid)
                if ev is not None:
                    events.append(ev)
        elif req.time_window_start is not None and req.time_window_end is not None:
            from src.models.event_search import EventSearchRequest
            search_req = EventSearchRequest(
                start_time=req.time_window_start,
                end_time=req.time_window_end,
            )
            search_resp = event_store.search(search_req)
            events = search_resp.events

        # Build sections
        timeline: List[TimelineEntry] = []
        layer_summaries: List[LayerSummaryEntry] = []
        provenance_records: List[ProvenanceRecord] = []

        if req.include_timeline and EvidencePackSection.TIMELINE in req.sections:
            timeline = sorted(
                [_event_to_timeline_entry(e) for e in events],
                key=lambda t: t.timestamp,
            )

        if req.include_layer_summaries and EvidencePackSection.LAYER_SUMMARY in req.sections:
            layer_summaries = _build_layer_summaries(events)

        if req.include_provenance and EvidencePackSection.PROVENANCE in req.sections:
            provenance_records = _build_provenance_records(events)

        # Determine time window from events if not explicitly set
        tw_start = req.time_window_start
        tw_end = req.time_window_end
        if events and tw_start is None:
            tw_start = min(e.event_time for e in events)
        if events and tw_end is None:
            tw_end = max(e.event_time for e in events)

        pack = EvidencePack(
            title=req.title,
            description=req.description,
            investigation_id=req.investigation_id,
            created_by=req.created_by,
            time_window_start=tw_start,
            time_window_end=tw_end,
            sections_included=list(req.sections),
            timeline=timeline,
            layer_summaries=layer_summaries,
            provenance_records=provenance_records,
            event_ids=[e.event_id for e in events],
            evidence_links=inv_evidence_links,
            notes=inv_notes,
            total_events=len(events),
            export_format=req.export_format,
        )

        with self._lock:
            self._packs[pack.pack_id] = pack
        return pack

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def get_pack(self, pack_id: str) -> Optional[EvidencePack]:
        with self._lock:
            return self._packs.get(pack_id)

    def list_packs(self, investigation_id: Optional[str] = None) -> List[EvidencePack]:
        with self._lock:
            items = list(self._packs.values())
        if investigation_id is not None:
            items = [p for p in items if p.investigation_id == investigation_id]
        items.sort(key=lambda p: p.created_at, reverse=True)
        return items

    def delete_pack(self, pack_id: str) -> bool:
        with self._lock:
            return self._packs.pop(pack_id, None) is not None

    def clear(self) -> None:
        """Remove all packs — used in tests."""
        with self._lock:
            self._packs.clear()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render_pack(self, pack: EvidencePack, format_: EvidencePackFormat) -> bytes:
        """Render the pack to bytes in the requested format."""
        if format_ == EvidencePackFormat.JSON:
            return self._render_json(pack)
        if format_ == EvidencePackFormat.MARKDOWN:
            return self._render_markdown(pack)
        if format_ == EvidencePackFormat.GEOJSON:
            return self._render_geojson(pack)
        # Fallback — should never be reached with correct enum values
        return self._render_json(pack)

    # ── Private renderers ─────────────────────────────────────────────────────

    @staticmethod
    def _render_json(pack: EvidencePack) -> bytes:
        return json.dumps(pack.model_dump(mode="json"), indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _render_markdown(pack: EvidencePack) -> bytes:
        lines: List[str] = []
        lines.append(f"# Evidence Pack: {pack.title}")
        lines.append("")
        lines.append(f"Generated: {pack.created_at.isoformat()}")
        lines.append(f"Investigation: {pack.investigation_id or 'standalone'}")
        tw_start = pack.time_window_start.isoformat() if pack.time_window_start else "N/A"
        tw_end = pack.time_window_end.isoformat() if pack.time_window_end else "N/A"
        lines.append(f"Time Window: {tw_start} — {tw_end}")
        if pack.description:
            lines.append(f"Description: {pack.description}")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"Total Events: {pack.total_events}")
        sections_str = ", ".join(s.value for s in pack.sections_included)
        lines.append(f"Sections: {sections_str or 'none'}")
        lines.append("")

        lines.append("## Timeline")
        if pack.timeline:
            lines.append("| Timestamp | Layer | Event Type | Source | Summary |")
            lines.append("|-----------|-------|------------|--------|---------|")
            for entry in pack.timeline:
                ts = entry.timestamp.isoformat()
                lines.append(
                    f"| {ts} | {entry.layer} | {entry.event_type} | {entry.source} | {entry.summary} |"
                )
        else:
            lines.append("_No timeline entries._")
        lines.append("")

        lines.append("## Layer Summary")
        if pack.layer_summaries:
            lines.append("| Layer | Event Count | Sources |")
            lines.append("|-------|-------------|---------|")
            for ls in pack.layer_summaries:
                sources_str = ", ".join(ls.sources)
                lines.append(f"| {ls.layer_name} | {ls.event_count} | {sources_str} |")
        else:
            lines.append("_No layer summaries._")
        lines.append("")

        lines.append("## Provenance")
        if pack.provenance_records:
            lines.append("| Source Name | Source Type | Event Count | License |")
            lines.append("|-------------|-------------|-------------|---------|")
            for pr in pack.provenance_records:
                lines.append(
                    f"| {pr.source_name} | {pr.source_type} | {pr.event_count} | {pr.license or 'N/A'} |"
                )
        else:
            lines.append("_No provenance records._")
        lines.append("")

        lines.append("## Notes")
        if pack.notes:
            for note in pack.notes:
                lines.append(f"- {note}")
        else:
            lines.append("_No notes._")
        lines.append("")

        return "\n".join(lines).encode("utf-8")

    @staticmethod
    def _render_geojson(pack: EvidencePack) -> bytes:
        """Build a GeoJSON FeatureCollection from evidence links and timeline geometries."""
        features: List[dict] = []

        # Extract any geometry from evidence_links
        for link in pack.evidence_links:
            geom = link.get("geometry")
            if geom:
                features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "evidence_id": link.get("evidence_id"),
                        "layer_type": link.get("layer_type"),
                        "description": link.get("description"),
                    },
                })

        fc = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "pack_id": pack.pack_id,
                "title": pack.title,
                "total_events": pack.total_events,
            },
        }
        return json.dumps(fc, ensure_ascii=False).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Process-wide singleton
# ──────────────────────────────────────────────────────────────────────────────

_default_service: Optional[EvidencePackService] = None
_singleton_lock = threading.Lock()


def get_default_evidence_pack_service() -> EvidencePackService:
    """Return the process-wide EvidencePackService singleton."""
    global _default_service
    if _default_service is None:
        with _singleton_lock:
            if _default_service is None:
                _default_service = EvidencePackService()
    return _default_service
