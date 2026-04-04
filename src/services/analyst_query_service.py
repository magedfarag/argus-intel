"""Analyst query execution and briefing generation service — Phase 5 Track C.

Thread-safe in-memory service. Executes structured queries against the
canonical event store and generates data-backed narrative briefings with
full provenance citations.

No external LLM calls — all outputs are deterministic from stored data.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.models.analyst_query import (
    AnalystQuery,
    BriefingOutput,
    BriefingRequest,
    BriefingSection,
    QueryFieldType,
    QueryOperator,
    QueryResult,
)
from src.models.canonical_event import EventType
from src.services.event_store import get_default_event_store


# ──────────────────────────────────────────────────────────────────────────────
# Threat indicator event types
# ──────────────────────────────────────────────────────────────────────────────

_THREAT_EVENT_TYPES = {
    EventType.STRIKE_EVENT.value,
    EventType.GPS_JAMMING_EVENT.value,
    EventType.DARK_SHIP_CANDIDATE.value,
}


# ──────────────────────────────────────────────────────────────────────────────
# Filter evaluation helpers
# ──────────────────────────────────────────────────────────────────────────────


def _matches_filter(event: Any, filt: Any) -> bool:
    """Return True if *event* satisfies *filt*."""
    field = filt.field
    op = filt.operator
    value = filt.value

    if field == QueryFieldType.EVENT_TYPE:
        event_val = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        if op == "eq":
            return event_val == value
        return False

    if field == QueryFieldType.SOURCE_TYPE:
        source_val = event.source_type.value if hasattr(event.source_type, "value") else str(event.source_type)
        if op == "eq":
            return source_val == value
        return False

    if field == QueryFieldType.ENTITY_ID:
        entity_id = event.entity_id
        if op in ("eq", "contains"):
            if entity_id is None:
                return False
            if op == "eq":
                return entity_id == value
            return str(value) in str(entity_id)
        return False

    if field == QueryFieldType.TIME_RANGE:
        # value must be {"start": ISO, "end": ISO}
        if not isinstance(value, dict):
            return False
        try:
            start_str = value.get("start")
            end_str = value.get("end")
            t_start = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else None
            t_end = datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else None
            if t_start and event.event_time < t_start:
                return False
            if t_end and event.event_time > t_end:
                return False
            return True
        except (AttributeError, ValueError):
            return False

    if field == QueryFieldType.CONFIDENCE:
        conf = event.confidence
        if conf is None:
            return False
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return False
        if op == "gte":
            return conf >= threshold
        if op == "lte":
            return conf <= threshold
        if op == "eq":
            return conf == threshold
        return False

    if field == QueryFieldType.GEOMETRY:
        # Spatial filter: basic bounding-box containment check.
        # value: {"bbox": [min_lon, min_lat, max_lon, max_lat]}
        if not isinstance(value, dict):
            return False
        bbox = value.get("bbox")
        if not bbox or len(bbox) < 4:
            return True  # no bbox given → pass all
        centroid = event.centroid
        if not centroid or centroid.get("type") != "Point":
            return False
        coords = centroid.get("coordinates", [])
        if len(coords) < 2:
            return False
        lon, lat = coords[0], coords[1]
        min_lon, min_lat, max_lon, max_lat = bbox[0], bbox[1], bbox[2], bbox[3]
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    if field == QueryFieldType.TEXT:
        # Substring match in string representation of event payload
        payload_str = str(event.attributes)
        if op == "contains":
            return str(value).lower() in payload_str.lower()
        # default: substring match
        return str(value).lower() in payload_str.lower()

    return False


def _event_passes(event: Any, query: AnalystQuery) -> bool:
    """Apply all filters with the query's combine_with logic."""
    if not query.filters:
        return True

    if query.combine_with == QueryOperator.NOT:
        # NOT: event must fail every filter
        return not any(_matches_filter(event, f) for f in query.filters)

    if query.combine_with == QueryOperator.OR:
        return any(_matches_filter(event, f) for f in query.filters)

    # AND (default)
    return all(_matches_filter(event, f) for f in query.filters)


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────


class AnalystQueryService:
    """Thread-safe in-memory analyst query and briefing service."""

    def __init__(self) -> None:
        self._saved_queries: Dict[str, AnalystQuery] = {}
        self._briefings: Dict[str, BriefingOutput] = {}
        self._lock = threading.Lock()

    # ── Query execution ────────────────────────────────────────────────────────

    def execute_query(self, query: AnalystQuery) -> QueryResult:
        """Execute the analyst query against the event store."""
        store = get_default_event_store()
        with store._lock:
            all_events = list(store._events.values())

        if not all_events:
            return QueryResult(
                query_id=query.query_id,
                total_matched=0,
                returned_count=0,
                events=[],
                sources_cited=[],
                confidence_range=None,
            )

        # Apply top-level time window if set
        candidates = all_events
        if query.time_window_start:
            candidates = [e for e in candidates if e.event_time >= query.time_window_start]
        if query.time_window_end:
            candidates = [e for e in candidates if e.event_time <= query.time_window_end]

        # Apply filter logic
        matched = [e for e in candidates if _event_passes(e, query)]

        # Sort newest-first
        matched.sort(key=lambda e: e.event_time, reverse=True)

        total = len(matched)
        limited = matched[: query.limit]

        # Collect provenance sources
        sources_cited: List[str] = sorted(
            {e.provenance.raw_source_ref.split("/")[0] if "/" in e.provenance.raw_source_ref else e.source for e in limited}
        )
        # Also include source field
        source_names = sorted({e.source for e in limited})
        sources_cited = sorted(set(sources_cited) | set(source_names))

        # Confidence range
        confidences = [e.confidence for e in limited if e.confidence is not None]
        conf_range: Optional[tuple] = (min(confidences), max(confidences)) if confidences else None

        event_dicts: List[dict] = []
        for e in limited:
            d = e.model_dump()
            if not query.include_provenance:
                d.pop("provenance", None)
                d.pop("normalization", None)
                d.pop("license", None)
            event_dicts.append(d)

        return QueryResult(
            query_id=query.query_id,
            total_matched=total,
            returned_count=len(limited),
            events=event_dicts,
            sources_cited=sources_cited,
            confidence_range=conf_range,
        )

    # ── Saved query CRUD ───────────────────────────────────────────────────────

    def save_query(self, query: AnalystQuery) -> AnalystQuery:
        with self._lock:
            self._saved_queries[query.query_id] = query
        return query

    def get_saved_query(self, query_id: str) -> Optional[AnalystQuery]:
        with self._lock:
            return self._saved_queries.get(query_id)

    def list_saved_queries(self) -> List[AnalystQuery]:
        with self._lock:
            return list(self._saved_queries.values())

    def delete_saved_query(self, query_id: str) -> bool:
        with self._lock:
            return self._saved_queries.pop(query_id, None) is not None

    # ── Briefing generation ────────────────────────────────────────────────────

    def generate_briefing(self, req: BriefingRequest) -> BriefingOutput:
        """Generate a data-backed analyst briefing from the event store."""
        events = self._collect_events_for_briefing(req)

        # Time window string for narratives
        t_start = req.time_window_start
        t_end = req.time_window_end
        if events:
            times = [e.event_time for e in events]
            t_start = t_start or min(times)
            t_end = t_end or max(times)
        time_window_str = (
            f"{t_start.strftime('%Y-%m-%dT%H:%M:%SZ') if t_start else 'N/A'} to "
            f"{t_end.strftime('%Y-%m-%dT%H:%M:%SZ') if t_end else 'N/A'}"
        )

        # Absence signals
        absence_signals = self._get_absence_signals(t_start, t_end)

        # Generate section narratives
        content: Dict[str, str] = {}
        for section in req.sections:
            content[section.value] = self._generate_section(
                section, events, absence_signals, time_window_str
            )

        # Build citations
        citations = [
            {
                "source": e.source,
                "event_id": e.event_id,
                "timestamp": e.event_time.isoformat(),
            }
            for e in events
        ]

        # Data summary
        by_type: Dict[str, int] = {}
        for e in events:
            by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
        sources_used = sorted({e.source for e in events})
        data_summary = {
            "event_count_by_type": by_type,
            "sources_used": sources_used,
            "time_range": time_window_str,
            "total_events": len(events),
        }

        # Confidence assessment
        confidences = [e.confidence for e in events if e.confidence is not None]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        if avg_conf >= 0.7:
            confidence_assessment = "high"
        elif avg_conf >= 0.4:
            confidence_assessment = "medium"
        else:
            confidence_assessment = "low"

        briefing = BriefingOutput(
            title=req.title,
            created_by=req.created_by,
            classification_label=req.classification_label,
            investigation_id=req.investigation_id,
            sections_generated=list(req.sections),
            content=content,
            citations=citations,
            data_summary=data_summary,
            raw_event_count=len(events),
            confidence_assessment=confidence_assessment,
        )
        with self._lock:
            self._briefings[briefing.briefing_id] = briefing
        return briefing

    def _collect_events_for_briefing(self, req: BriefingRequest) -> list:
        """Collect events for briefing generation per priority order."""
        store = get_default_event_store()

        if req.investigation_id:
            # Get events linked to the investigation
            try:
                from src.services.investigation_service import get_default_investigation_store
                inv = get_default_investigation_store().get(req.investigation_id)
                if inv and inv.linked_event_ids:
                    events = [store.get(eid) for eid in inv.linked_event_ids]
                    return [e for e in events if e is not None]
            except Exception:
                pass

        if req.query:
            result = self.execute_query(req.query)
            # Re-fetch full event objects from result event_ids
            event_ids = [e.get("event_id") for e in result.events if e.get("event_id")]
            return [store.get(eid) for eid in event_ids if store.get(eid) is not None]

        with store._lock:
            all_events = list(store._events.values())

        if req.time_window_start or req.time_window_end:
            filtered = all_events
            if req.time_window_start:
                filtered = [e for e in filtered if e.event_time >= req.time_window_start]
            if req.time_window_end:
                filtered = [e for e in filtered if e.event_time <= req.time_window_end]
            filtered.sort(key=lambda e: e.event_time, reverse=True)
            return filtered

        # Fallback: last 100 events by time
        all_events.sort(key=lambda e: e.event_time, reverse=True)
        return all_events[:100]

    def _get_absence_signals(self, t_start: Optional[datetime], t_end: Optional[datetime]) -> list:
        """Retrieve active absence signals from the absence analytics service."""
        try:
            from src.services.absence_analytics import get_default_absence_service
            svc = get_default_absence_service()
            signals = svc.list_signals()
            if t_start:
                signals = [s for s in signals if s.gap_start >= t_start or s.gap_end is None]
            if t_end:
                signals = [s for s in signals if s.gap_start <= t_end]
            return signals
        except Exception:
            return []

    def _generate_section(
        self,
        section: BriefingSection,
        events: list,
        absence_signals: list,
        time_window_str: str,
    ) -> str:
        """Generate narrative text for a single briefing section."""
        n = len(events)
        sources = sorted({e.source for e in events})
        n_high = sum(1 for e in events if e.confidence is not None and e.confidence >= 0.7)

        if section == BriefingSection.EXECUTIVE_SUMMARY:
            n_absence = len(absence_signals)
            return (
                f"During {time_window_str}, {n} event(s) were recorded from "
                f"{len(sources)} source(s) ({', '.join(sources) or 'none'}). "
                f"{n_high} high-confidence event(s) detected. "
                f"{n_absence} absence signal(s) flagged."
            )

        if section == BriefingSection.ENTITY_ACTIVITY:
            entity_counts: Dict[str, int] = {}
            entity_last: Dict[str, datetime] = {}
            for e in events:
                eid = e.entity_id or "(unknown)"
                entity_counts[eid] = entity_counts.get(eid, 0) + 1
                if eid not in entity_last or e.event_time > entity_last[eid]:
                    entity_last[eid] = e.event_time
            if not entity_counts:
                return "No entity activity recorded in this window."
            lines = []
            for eid, count in sorted(entity_counts.items(), key=lambda x: -x[1]):
                last_seen = entity_last[eid].strftime("%Y-%m-%dT%H:%M:%SZ")
                lines.append(f"Entity {eid}: {count} event(s), last seen {last_seen}.")
            return "\n".join(lines)

        if section == BriefingSection.THREAT_INDICATORS:
            threats = [
                e for e in events
                if e.event_type.value in _THREAT_EVENT_TYPES
                or (e.confidence is not None and e.confidence >= 0.7)
            ]
            if not threats:
                return "No significant threat indicators detected in this window."
            lines = []
            for e in sorted(threats, key=lambda x: -(x.confidence or 0.0)):
                conf_str = f"{e.confidence:.2f}" if e.confidence is not None else "N/A"
                lines.append(
                    f"[{e.event_type.value}] {e.event_id} | "
                    f"source={e.source} | confidence={conf_str} | "
                    f"time={e.event_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                )
            return "\n".join(lines)

        if section == BriefingSection.TIMELINE:
            top = sorted(events, key=lambda e: -(e.confidence or 0.0))[:10]
            top_by_time = sorted(top, key=lambda e: e.event_time)
            if not top_by_time:
                return "No events available for timeline."
            lines = []
            for e in top_by_time:
                conf_str = f"{e.confidence:.2f}" if e.confidence is not None else "N/A"
                lines.append(
                    f"{e.event_time.strftime('%Y-%m-%dT%H:%M:%SZ')} | "
                    f"{e.event_type.value} | {e.source} | conf={conf_str}"
                )
            return "\n".join(lines)

        if section == BriefingSection.ABSENCE_SIGNALS:
            if not absence_signals:
                return "No absence signals active in this time window."
            lines = []
            for sig in absence_signals[:10]:
                entity = sig.entity_id or "(area)"
                gap_start = sig.gap_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                lines.append(
                    f"[{sig.signal_type.value}] entity={entity} | "
                    f"severity={sig.severity.value} | "
                    f"gap_start={gap_start} | conf={sig.confidence:.2f}"
                )
            total = len(absence_signals)
            header = f"{total} absence signal(s) active:"
            return header + "\n" + "\n".join(lines)

        if section == BriefingSection.SOURCE_ASSESSMENT:
            if not sources:
                return "No sources used in this briefing."
            source_counts: Dict[str, int] = {}
            for e in events:
                source_counts[e.source] = source_counts.get(e.source, 0) + 1
            lines = []
            for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
                # Extract license info from first event of this source
                src_events = [e for e in events if e.source == src]
                license_tier = src_events[0].license.access_tier if src_events else "unknown"
                lines.append(f"Source: {src} | events={count} | access_tier={license_tier}")
            return "\n".join(lines)

        if section == BriefingSection.RECOMMENDATIONS:
            # Top entity by event count
            entity_counts_r: Dict[str, int] = {}
            for e in events:
                eid = e.entity_id or "(unknown)"
                entity_counts_r[eid] = entity_counts_r.get(eid, 0) + 1
            top_entity = (
                max(entity_counts_r, key=lambda x: entity_counts_r[x])
                if entity_counts_r
                else "(no entities)"
            )
            unresolved = sum(1 for s in absence_signals if s.gap_end is None)
            return (
                f"Increase monitoring of entity: {top_entity}. "
                f"Review {unresolved} unresolved absence signal(s)."
            )

        return f"Section {section.value} not generated."

    # ── Briefing CRUD ──────────────────────────────────────────────────────────

    def get_briefing(self, briefing_id: str) -> Optional[BriefingOutput]:
        with self._lock:
            return self._briefings.get(briefing_id)

    def list_briefings(self, investigation_id: Optional[str] = None) -> List[BriefingOutput]:
        with self._lock:
            items = list(self._briefings.values())
        if investigation_id is not None:
            items = [b for b in items if b.investigation_id == investigation_id]
        items.sort(key=lambda b: b.created_at, reverse=True)
        return items

    def export_briefing_text(self, briefing: BriefingOutput) -> str:
        """Export briefing as formatted text report with classification header/footer."""
        sep = "=" * 72
        lines = [
            sep,
            f"CLASSIFICATION: {briefing.classification_label}",
            sep,
            f"TITLE:          {briefing.title}",
            f"BRIEFING ID:    {briefing.briefing_id}",
            f"CREATED AT:     {briefing.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            f"CREATED BY:     {briefing.created_by or 'N/A'}",
            f"EVENTS USED:    {briefing.raw_event_count}",
            f"CONFIDENCE:     {briefing.confidence_assessment.upper()}",
            sep,
            "",
        ]
        for section in briefing.sections_generated:
            lines.append(f"## {section.value.replace('_', ' ').upper()}")
            lines.append(briefing.content.get(section.value, "(empty)"))
            lines.append("")
        lines += [
            sep,
            f"SOURCES: {', '.join(briefing.data_summary.get('sources_used', []))}",
            f"CITATIONS: {len(briefing.citations)} event(s) cited",
            sep,
            f"CLASSIFICATION: {briefing.classification_label}",
            sep,
        ]
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Singleton factory
# ──────────────────────────────────────────────────────────────────────────────

_default_service: "AnalystQueryService | None" = None
_singleton_lock = threading.Lock()


def get_default_analyst_query_service() -> AnalystQueryService:
    """Return the process-wide AnalystQueryService singleton."""
    global _default_service
    if _default_service is None:
        with _singleton_lock:
            if _default_service is None:
                _default_service = AnalystQueryService()
    return _default_service
