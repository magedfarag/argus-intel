import { useState } from "react";
import { useEventSearch } from "../../hooks/useEvents";
import type { CanonicalEvent, EventSearchRequest } from "../../api/types";
import { format } from "date-fns";

interface Props {
  aoiId: string | null;
  startTime: string;
  endTime: string;
  onEventSelect?: (event: CanonicalEvent) => void;
}

// P5-1.6: Configurable page size for frontend virtualisation
const PAGE_SIZE = 25;

export function SearchPanel({ aoiId, startTime, endTime, onEventSelect }: Props) {
  const [activeReq, setActiveReq] = useState<EventSearchRequest | null>(null);
  const [page, setPage] = useState(0);
  const { data: events = [], isLoading, error } = useEventSearch(activeReq);

  const totalPages = Math.ceil(events.length / PAGE_SIZE);
  const pageEvents = events.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSearch() {
    setPage(0);
    setActiveReq({
      ...(aoiId ? { aoi_id: aoiId } : {}),
      start_time: startTime,
      end_time: endTime,
      limit: 500, // request more; paginate client-side
    });
  }

  return (
    <div className="panel" data-testid="search-panel">
      <div className="panel-header">
        <h3 className="panel-title">Events</h3>
        <button className="btn btn-primary btn-sm" onClick={handleSearch} data-testid="search-btn">
          Search
        </button>
      </div>
      {isLoading && <p className="muted">Searching…</p>}
      {error && <p className="error">{String(error)}</p>}
      <ul className="event-list">
        {pageEvents.map((evt: CanonicalEvent) => (
          <li
            key={evt.event_id}
            className="event-item"
            onClick={() => onEventSelect?.(evt)}
            data-testid="event-item"
          >
            <span className={`event-badge event-badge--${evt.source_type}`}>{evt.source_type}</span>
            <span className="event-type">{evt.event_type.replace(/_/g, " ")}</span>
            <span className="event-time">{format(new Date(evt.event_time), "MM/dd HH:mm")}</span>
            {evt.confidence != null && (
              <span className="event-confidence">{Math.round(evt.confidence * 100)}%</span>
            )}
          </li>
        ))}
      </ul>
      {events.length === 0 && !isLoading && activeReq && <p className="muted">No events found</p>}
      {totalPages > 1 && (
        <div className="pagination" data-testid="pagination">
          <button
            className="btn btn-sm"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            data-testid="pagination-prev"
          >
            ‹
          </button>
          <span className="pagination-info" data-testid="pagination-info">
            {page + 1} / {totalPages}
          </span>
          <button
            className="btn btn-sm"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            data-testid="pagination-next"
          >
            ›
          </button>
        </div>
      )}
    </div>
  );
}
