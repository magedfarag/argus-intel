// API client for Phase 2 operational layer endpoints.
// Follows the same fetch + x-api-key pattern as client.ts.

import { getApiKey } from './client';
import type {
  SatelliteOrbit,
  SatellitePass,
  AirspaceRestriction,
  NotamEvent,
  GpsJammingEvent,
  HeatmapPoint,
  StrikeEvent,
} from '../types/operationalLayers';

const BASE = '';

async function opRequest<T>(
  path: string,
  signal?: AbortSignal,
  init: RequestInit = {},
): Promise<T> {
  const key = getApiKey();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> ?? {}),
  };
  if (key) headers['Authorization'] = `Bearer ${key}`;
  const res = await fetch(`${BASE}${path}`, { ...init, headers, signal });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Orbits ───────────────────────────────────────────────────────────────────

export function fetchOrbits(signal?: AbortSignal): Promise<SatelliteOrbit[]> {
  return opRequest<{ orbits: SatelliteOrbit[] }>('/api/v1/orbits', signal).then(r => r.orbits);
}

export function fetchSatellitePasses(
  satelliteId: string,
  lon: number,
  lat: number,
  horizonHours = 24,
  signal?: AbortSignal,
): Promise<SatellitePass[]> {
  const params = new URLSearchParams({
    lon: String(lon),
    lat: String(lat),
    horizon_hours: String(horizonHours),
  });
  return opRequest<SatellitePass[]>(
    `/api/v1/orbits/${encodeURIComponent(satelliteId)}/passes?${params}`,
    signal,
  );
}

// ── Airspace ──────────────────────────────────────────────────────────────────

export function fetchAirspaceRestrictions(
  activeOnly?: boolean,
  signal?: AbortSignal,
): Promise<AirspaceRestriction[]> {
  const params = new URLSearchParams();
  if (activeOnly !== undefined) params.set('active_only', String(activeOnly));
  const qs = params.toString() ? `?${params}` : '';
  return opRequest<{ restrictions: AirspaceRestriction[] }>(`/api/v1/airspace/restrictions${qs}`, signal).then(r => r.restrictions);
}

export function fetchNotams(icao?: string, signal?: AbortSignal): Promise<NotamEvent[]> {
  const params = new URLSearchParams();
  if (icao) params.set('icao', icao);
  const qs = params.toString() ? `?${params}` : '';
  return opRequest<{ notams: NotamEvent[] }>(`/api/v1/airspace/notams${qs}`, signal).then(r => r.notams);
}

// ── GPS Jamming ────────────────────────────────────────────────────────────────

export function fetchJammingEvents(
  confidenceMin?: number,
  signal?: AbortSignal,
): Promise<GpsJammingEvent[]> {
  const params = new URLSearchParams();
  if (confidenceMin !== undefined) params.set('confidence_min', String(confidenceMin));
  const qs = params.toString() ? `?${params}` : '';
  return opRequest<GpsJammingEvent[]>(`/api/v1/jamming/events${qs}`, signal);
}

export function fetchJammingHeatmap(signal?: AbortSignal): Promise<HeatmapPoint[]> {
  return opRequest<HeatmapPoint[]>('/api/v1/jamming/heatmap', signal);
}

// ── Strike Events ─────────────────────────────────────────────────────────────

export function fetchStrikeEvents(
  strikeType?: string,
  confidenceMin?: number,
  signal?: AbortSignal,
): Promise<StrikeEvent[]> {
  const params = new URLSearchParams();
  if (strikeType) params.set('strike_type', strikeType);
  if (confidenceMin !== undefined) params.set('confidence_min', String(confidenceMin));
  const qs = params.toString() ? `?${params}` : '';
  return opRequest<StrikeEvent[]>(`/api/v1/strikes${qs}`, signal);
}

export function fetchStrikeSummary(signal?: AbortSignal): Promise<Record<string, number>> {
  return opRequest<Record<string, number>>('/api/v1/strikes/summary', signal);
}
