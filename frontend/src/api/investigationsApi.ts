// API client for Phase 5 investigation workflow endpoints.
// Follows the same fetch + x-api-key pattern as operationalLayersApi.ts.

import { getApiKey } from './client';
import type {
  Investigation,
  InvestigationCreateRequest,
  WatchlistEntry,
  AbsenceSignal,
  AbsenceAlert,
} from '../types/investigations';

const BASE = '/api/v1';

async function invRequest<T>(
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

// ── Investigations ────────────────────────────────────────────────────────────

export async function fetchInvestigations(
  status?: string,
  signal?: AbortSignal,
): Promise<Investigation[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  const qs = params.toString() ? `?${params}` : '';
  const res = await invRequest<{ items: Investigation[]; total: number }>(`/investigations${qs}`, signal);
  return res.items;
}

export function createInvestigation(
  req: InvestigationCreateRequest,
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>('/investigations', signal, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export function fetchInvestigation(
  id: string,
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>(`/investigations/${encodeURIComponent(id)}`, signal);
}

export function updateInvestigation(
  id: string,
  patch: Partial<InvestigationCreateRequest & { status: string }>,
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>(`/investigations/${encodeURIComponent(id)}`, signal, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export function deleteInvestigation(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return invRequest<void>(`/investigations/${encodeURIComponent(id)}`, signal, {
    method: 'DELETE',
  });
}

export function addInvestigationNote(
  id: string,
  content: string,
  author?: string,
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>(`/investigations/${encodeURIComponent(id)}/notes`, signal, {
    method: 'POST',
    body: JSON.stringify({ content, author }),
  });
}

export function addWatchlistEntry(
  id: string,
  entry: Omit<WatchlistEntry, 'id' | 'added_at'>,
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>(`/investigations/${encodeURIComponent(id)}/watchlist`, signal, {
    method: 'POST',
    body: JSON.stringify(entry),
  });
}

export function addEvidenceLink(
  id: string,
  evidence: { evidence_id: string; source: string; url?: string; description?: string },
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>(`/investigations/${encodeURIComponent(id)}/evidence`, signal, {
    method: 'POST',
    body: JSON.stringify(evidence),
  });
}

export function exportInvestigation(
  id: string,
  signal?: AbortSignal,
): Promise<Investigation> {
  return invRequest<Investigation>(`/investigations/${encodeURIComponent(id)}/export`, signal);
}

// ── Absence Detection ─────────────────────────────────────────────────────────

export function fetchAbsenceSignals(
  opts?: { active_only?: boolean; signal_type?: string },
  signal?: AbortSignal,
): Promise<AbsenceSignal[]> {
  const params = new URLSearchParams();
  if (opts?.active_only !== undefined) params.set('active_only', String(opts.active_only));
  if (opts?.signal_type) params.set('signal_type', opts.signal_type);
  const qs = params.toString() ? `?${params}` : '';
  return invRequest<AbsenceSignal[]>(`/absence/signals${qs}`, signal);
}

export function fetchAbsenceAlerts(signal?: AbortSignal): Promise<AbsenceAlert[]> {
  return invRequest<AbsenceAlert[]>('/absence/alerts', signal);
}

// ── Evidence Packs ────────────────────────────────────────────────────────────

export function generateEvidencePack(
  investigation_id: string,
  signal?: AbortSignal,
): Promise<{ pack_id: string }> {
  return invRequest<{ pack_id: string }>('/evidence-packs', signal, {
    method: 'POST',
    body: JSON.stringify({ investigation_id }),
  });
}

export async function downloadEvidencePack(
  pack_id: string,
  format: 'json' | 'markdown' | 'geojson' = 'markdown',
  signal?: AbortSignal,
): Promise<string> {
  const key = getApiKey();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (key) headers['Authorization'] = `Bearer ${key}`;
  const res = await fetch(
    `${BASE}/evidence-packs/${encodeURIComponent(pack_id)}/download?format=${format}`,
    { headers, signal },
  );
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.text();
}

// ── Analyst Briefings ─────────────────────────────────────────────────────────

export function generateBriefing(
  investigation_id: string,
  title: string,
  signal?: AbortSignal,
): Promise<{ briefing_id: string }> {
  return invRequest<{ briefing_id: string }>('/analyst/briefings', signal, {
    method: 'POST',
    body: JSON.stringify({ investigation_id, title }),
  });
}

export async function fetchBriefingText(
  briefing_id: string,
  signal?: AbortSignal,
): Promise<string> {
  const key = getApiKey();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (key) headers['Authorization'] = `Bearer ${key}`;
  const res = await fetch(
    `${BASE}/analyst/briefings/${encodeURIComponent(briefing_id)}/text`,
    { headers, signal },
  );
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.text();
}
