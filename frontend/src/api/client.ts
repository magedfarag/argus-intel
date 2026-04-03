// Typed API client for the Construction Activity Monitor backend
// All requests include x-api-key when configured (P1-1.8)

import type {
  Aoi, CreateAoiRequest,
  CanonicalEvent, EventSearchRequest, TimelineBucket,
  ImagerySearchRequest, ImageryItem,
  ChangeCandidate, ChangeDetectionJob, ReviewDecision,
  ExportRequest, ExportJob,
  PlaybackQueryRequest, PlaybackQueryResponse,
  ProviderStatus,
} from './types';

const BASE = '';   // proxy forwards /api -> backend; set full URL when deploying standalone

export function getApiKey(): string {
  return localStorage.getItem('geoint_api_key') ?? '';
}

export function setApiKey(key: string): void {
  localStorage.setItem('geoint_api_key', key);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const key = getApiKey();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> ?? {}),
  };
  if (key) headers['x-api-key'] = key;
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── AOIs ────────────────────────────────────────────────────────────────────
export const aoisApi = {
  list: () => request<Aoi[]>('/api/v1/aois'),
  get: (id: string) => request<Aoi>(`/api/v1/aois/${id}`),
  create: (body: CreateAoiRequest) =>
    request<Aoi>('/api/v1/aois', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: Partial<CreateAoiRequest>) =>
    request<Aoi>(`/api/v1/aois/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (id: string) =>
    request<void>(`/api/v1/aois/${id}`, { method: 'DELETE' }),
};

// ── Events ───────────────────────────────────────────────────────────────────
export const eventsApi = {
  search: (body: EventSearchRequest) =>
    request<CanonicalEvent[]>('/api/v1/events/search', { method: 'POST', body: JSON.stringify(body) }),
  get: (id: string) => request<CanonicalEvent>(`/api/v1/events/${id}`),
  timeline: (params: Record<string, string>) =>
    request<TimelineBucket[]>(`/api/v1/events/timeline?${new URLSearchParams(params)}`),
  sources: () => request<string[]>('/api/v1/events/sources'),
};

// ── Imagery ──────────────────────────────────────────────────────────────────
export const imageryApi = {
  search: (body: ImagerySearchRequest) =>
    request<ImageryItem[]>('/api/v1/imagery/search', { method: 'POST', body: JSON.stringify(body) }),
  providers: () => request<ProviderStatus[]>('/api/v1/imagery/providers'),
};

// ── Analytics ────────────────────────────────────────────────────────────────
export const analyticsApi = {
  submitJob: (aoiId: string) =>
    request<ChangeDetectionJob>('/api/v1/analytics/change-detection', {
      method: 'POST', body: JSON.stringify({ aoi_id: aoiId }),
    }),
  getJob: (jobId: string) =>
    request<ChangeDetectionJob>(`/api/v1/analytics/change-detection/${jobId}`),
  getCandidates: (jobId: string) =>
    request<ChangeCandidate[]>(`/api/v1/analytics/change-detection/${jobId}/candidates`),
  review: (candidateId: string, decision: ReviewDecision, notes?: string, analystId?: string) =>
    request<ChangeCandidate>(`/api/v1/analytics/change-detection/${candidateId}/review`, {
      method: 'PUT',
      body: JSON.stringify({ decision, notes, analyst_id: analystId }),
    }),
  reviewQueue: (aoiId?: string) =>
    request<ChangeCandidate[]>(`/api/v1/analytics/review${aoiId ? `?aoi_id=${aoiId}` : ''}`),
  evidencePack: (candidateId: string) =>
    request<unknown>(`/api/v1/analytics/change-detection/${candidateId}/evidence-pack`),
};

// ── Exports ──────────────────────────────────────────────────────────────────
export const exportsApi = {
  create: (body: ExportRequest) =>
    request<ExportJob>('/api/v1/exports', { method: 'POST', body: JSON.stringify(body) }),
  get: (jobId: string) => request<ExportJob>(`/api/v1/exports/${jobId}`),
};

// ── Playback ─────────────────────────────────────────────────────────────────
export const playbackApi = {
  query: (body: PlaybackQueryRequest) =>
    request<PlaybackQueryResponse>('/api/v1/playback/query', { method: 'POST', body: JSON.stringify(body) }),
};

// ── Health Dashboard (P5-3.1, P5-3.5) ───────────────────────────────────────
export const healthApi = {
  dashboard: () => request<import('./types').HealthDashboardResponse>('/api/v1/health/sources'),
  connector: (id: string) => request<import('./types').SourceHealthRecord>(`/api/v1/health/sources/${id}`),
  alerts: (includeResolved = false) =>
    request<import('./types').HealthAlert[]>(`/api/v1/health/alerts?include_resolved=${includeResolved}`),
  usage: () => request<import('./types').UsagePeriod[]>('/api/v1/health/usage'),
};

// ── System ───────────────────────────────────────────────────────────────────
export const systemApi = {
  health: () => request<{ status: string }>('/healthz'),
  providers: () => request<{ providers: ProviderStatus[] }>('/api/providers'),
  config: () => request<Record<string, unknown>>('/api/config'),
};
