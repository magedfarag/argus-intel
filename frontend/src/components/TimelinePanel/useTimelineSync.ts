// useTimelineSync — Track E cross-layer synchronization hook.
// Provides a shared time window and per-layer filter helpers so that
// GlobeView, MapView, and all panel components stay temporally consistent.

import { useState, useCallback } from 'react';
import type { GpsJammingEvent, StrikeEvent, AirspaceRestriction } from '../../types/operationalLayers';

// ── Public types ──────────────────────────────────────────────────────────────

export interface TimelineState {
  currentTime: Date;
  windowStart: Date;
  windowEnd: Date;
}

const WINDOW_MS = 24 * 60 * 60 * 1000; // 24 h

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTimelineSync(): {
  timelineState: TimelineState;
  setCurrentTime: (t: Date) => void;
  currentTimeUnix: number;
  isEventVisible: (eventTime: string) => boolean;
  filteredJammingEvents: (events: GpsJammingEvent[]) => GpsJammingEvent[];
  filteredStrikes: (events: StrikeEvent[]) => StrikeEvent[];
  filteredAirspaceRestrictions: (restrictions: AirspaceRestriction[]) => AirspaceRestriction[];
} {
  const [currentTime, setCurrentTimeState] = useState<Date>(() => new Date());

  const windowEnd = currentTime;
  const windowStart = new Date(currentTime.getTime() - WINDOW_MS);

  const timelineState: TimelineState = { currentTime, windowStart, windowEnd };

  const currentTimeUnix = currentTime.getTime() / 1000;

  const setCurrentTime = useCallback((t: Date) => {
    setCurrentTimeState(t);
  }, []);

  const isEventVisible = useCallback(
    (eventTime: string): boolean => {
      const t = new Date(eventTime).getTime();
      return t >= windowStart.getTime() && t <= windowEnd.getTime();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [windowStart.getTime(), windowEnd.getTime()],
  );

  const filteredJammingEvents = useCallback(
    (events: GpsJammingEvent[]): GpsJammingEvent[] =>
      events.filter(e => isEventVisible(e.detected_at)),
    [isEventVisible],
  );

  const filteredStrikes = useCallback(
    (events: StrikeEvent[]): StrikeEvent[] =>
      events.filter(e => isEventVisible(e.occurred_at)),
    [isEventVisible],
  );

  const filteredAirspaceRestrictions = useCallback(
    (restrictions: AirspaceRestriction[]): AirspaceRestriction[] =>
      restrictions.filter(r => {
        const from = new Date(r.valid_from).getTime();
        const to = r.valid_to ? new Date(r.valid_to).getTime() : Infinity;
        // Include restriction if its validity window overlaps with [windowStart, windowEnd]
        return from <= windowEnd.getTime() && to >= windowStart.getTime();
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [windowStart.getTime(), windowEnd.getTime()],
  );

  return {
    timelineState,
    setCurrentTime,
    currentTimeUnix,
    isEventVisible,
    filteredJammingEvents,
    filteredStrikes,
    filteredAirspaceRestrictions,
  };
}
