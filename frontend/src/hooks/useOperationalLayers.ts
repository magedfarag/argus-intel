// React hooks for Phase 2 operational layers.
// Each hook fetches on mount, cancels on unmount via AbortController,
// and exposes loading + error state.

import { useEffect, useState } from 'react';
import {
  fetchOrbits,
  fetchSatellitePasses,
  fetchAirspaceRestrictions,
  fetchNotams,
  fetchJammingEvents,
  fetchJammingHeatmap,
  fetchStrikeEvents,
  fetchStrikeSummary,
} from '../api/operationalLayersApi';
import type {
  SatelliteOrbit,
  SatellitePass,
  AirspaceRestriction,
  NotamEvent,
  GpsJammingEvent,
  HeatmapPoint,
  StrikeEvent,
} from '../types/operationalLayers';

// ── Orbit layer ───────────────────────────────────────────────────────────────

export function useOrbits(): {
  orbits: SatelliteOrbit[];
  loading: boolean;
  error: string | null;
} {
  const [orbits, setOrbits] = useState<SatelliteOrbit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchOrbits(controller.signal)
      .then(setOrbits)
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, []);

  return { orbits, loading, error };
}

// ── Airspace layer ────────────────────────────────────────────────────────────

export function useAirspaceRestrictions(activeOnly?: boolean): {
  restrictions: AirspaceRestriction[];
  notams: NotamEvent[];
  loading: boolean;
} {
  const [restrictions, setRestrictions] = useState<AirspaceRestriction[]>([]);
  const [notams, setNotams] = useState<NotamEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    Promise.all([
      fetchAirspaceRestrictions(activeOnly, controller.signal),
      fetchNotams(undefined, controller.signal),
    ])
      .then(([r, n]) => {
        setRestrictions(r);
        setNotams(n);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          // Non-fatal: leave previous data in place on refresh failure
          console.error('[useAirspaceRestrictions]', err);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [activeOnly]);

  return { restrictions, notams, loading };
}

// ── GPS Jamming layer ─────────────────────────────────────────────────────────

export function useJammingLayer(confidenceMin?: number): {
  events: GpsJammingEvent[];
  heatmapPoints: HeatmapPoint[];
  loading: boolean;
} {
  const [events, setEvents] = useState<GpsJammingEvent[]>([]);
  const [heatmapPoints, setHeatmapPoints] = useState<HeatmapPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    Promise.all([
      fetchJammingEvents(confidenceMin, controller.signal),
      fetchJammingHeatmap(controller.signal),
    ])
      .then(([evts, pts]) => {
        setEvents(evts);
        setHeatmapPoints(pts);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          console.error('[useJammingLayer]', err);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [confidenceMin]);

  return { events, heatmapPoints, loading };
}

// ── Strike layer ──────────────────────────────────────────────────────────────

export function useStrikeLayer(strikeType?: string): {
  strikes: StrikeEvent[];
  summary: Record<string, number>;
  loading: boolean;
} {
  const [strikes, setStrikes] = useState<StrikeEvent[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    Promise.all([
      fetchStrikeEvents(strikeType, undefined, controller.signal),
      fetchStrikeSummary(controller.signal),
    ])
      .then(([evts, sum]) => {
        setStrikes(evts);
        setSummary(sum);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          console.error('[useStrikeLayer]', err);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [strikeType]);

  return { strikes, summary, loading };
}

// ── Satellite passes ──────────────────────────────────────────────────────────

export function useSatellitePasses(
  satelliteId: string | null,
  lon: number,
  lat: number,
  horizonHours?: number,
): { passes: SatellitePass[]; loading: boolean; error: string | null } {
  const [passes, setPasses] = useState<SatellitePass[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!satelliteId) {
      setPasses([]);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchSatellitePasses(satelliteId, lon, lat, horizonHours ?? 24, controller.signal)
      .then(setPasses)
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [satelliteId, lon, lat, horizonHours]);

  return { passes, loading, error };
}

export function useAllSatellitePasses(
  orbits: SatelliteOrbit[],
  lon: number,
  lat: number,
  horizonHours?: number,
): { passes: SatellitePass[]; loading: boolean; error: string | null } {
  const [passes, setPasses] = useState<SatellitePass[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (orbits.length === 0) {
      setPasses([]);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    Promise.all(
      orbits.map(o =>
        fetchSatellitePasses(o.satellite_id, lon, lat, horizonHours ?? 24, controller.signal),
      ),
    )
      .then(results => setPasses(results.flat()))
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [orbits, lon, lat, horizonHours]); // eslint-disable-line react-hooks/exhaustive-deps

  return { passes, loading, error };
}

