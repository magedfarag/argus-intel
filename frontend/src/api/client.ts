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
  ChokepointListResponse, ChokepointMetricsResponse,
  VesselProfile, DarkShipDetectionResponse, IntelBriefing,
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
  if (key) headers['Authorization'] = `Bearer ${key}`;
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
  list: async (): Promise<Aoi[]> => {
    const res = await request<{ items: Aoi[] }>('/api/v1/aois');
    return res.items;
  },
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
  search: async (body: EventSearchRequest): Promise<CanonicalEvent[]> => {
    const res = await request<{ events: CanonicalEvent[] }>('/api/v1/events/search', { method: 'POST', body: JSON.stringify(body) });
    return res.events;
  },
  get: (id: string) => request<CanonicalEvent>(`/api/v1/events/${id}`),
  timeline: async (params: Record<string, string>): Promise<TimelineBucket[]> => {
    // Backend returns { buckets: [{ bucket_start, bucket_end, count, by_type }] }
    // Frontend expects [{ time, count, source }] — one row per source per bucket.
    interface BackendBucket {
      bucket_start: string;
      bucket_end: string;
      count: number;
      by_type: Record<string, number>;
    }
    const res = await request<{ buckets: BackendBucket[] }>(`/api/v1/events/timeline?${new URLSearchParams(params)}`);
    const flat: TimelineBucket[] = [];
    for (const b of res.buckets) {
      const entries = Object.entries(b.by_type);
      if (entries.length === 0) {
        // No breakdown — emit a single row if count > 0
        if (b.count > 0) flat.push({ time: b.bucket_start, count: b.count, source: 'unknown' });
      } else {
        for (const [src, cnt] of entries) {
          if (cnt > 0) flat.push({ time: b.bucket_start, count: cnt, source: src });
        }
      }
    }
    return flat;
  },
  sources: () => request<string[]>('/api/v1/events/sources'),
};

// ── Imagery ──────────────────────────────────────────────────────────────────
export const imageryApi = {
  search: async (body: ImagerySearchRequest): Promise<ImageryItem[]> => {
    // Backend returns { total_items, items: ImageryItemSummary[], connector_summaries }
    // Frontend expects ImageryItem[] — unwrap and transform field names.
    interface BackendItem {
      event_id: string;
      source: string;
      connector_id: string;
      event_time: string;
      cloud_cover_pct?: number;
      geometry: unknown;
      scene_url?: string;
      [k: string]: unknown;
    }
    const res = await request<{ items: BackendItem[] }>('/api/v1/imagery/search', {
      method: 'POST', body: JSON.stringify(body),
    });
    return (res.items ?? []).map(i => ({
      item_id: i.event_id,
      collection: i.source ?? i.connector_id,
      provider: i.connector_id,
      datetime: i.event_time,
      cloud_cover: i.cloud_cover_pct,
      geometry: i.geometry as ImageryItem['geometry'],
      thumbnail_url: i.scene_url,
    }));
  },
  providers: () => request<ProviderStatus[]>('/api/v1/imagery/providers'),
};

// ── Analytics ────────────────────────────────────────────────────────────────
export const analyticsApi = {
  submitJob: (aoiId: string, startDate?: string, endDate?: string) =>
    request<ChangeDetectionJob>('/api/v1/analytics/change-detection', {
      method: 'POST', body: JSON.stringify({
        aoi_id: aoiId,
        start_date: startDate ?? new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10),
        end_date: endDate ?? new Date().toISOString().slice(0, 10),
      }),
    }),
  getJob: (jobId: string) =>
    request<ChangeDetectionJob>(`/api/v1/analytics/change-detection/${jobId}`),
  getCandidates: (jobId: string) =>
    request<ChangeCandidate[]>(`/api/v1/analytics/change-detection/${jobId}/candidates`),
  review: (candidateId: string, decision: ReviewDecision, notes?: string, analystId?: string) =>
    request<ChangeCandidate>(`/api/v1/analytics/change-detection/${candidateId}/review`, {
      method: 'PUT',
      body: JSON.stringify({ disposition: decision, notes, analyst_id: analystId }),
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
  fullHealth: () => request<{
    status: string;
    mode: string;
    demo_available: boolean;
    redis: string;
    celery_worker: string;
    providers: Record<string, string>;
    version?: string;
    circuit_breakers: Record<string, string>;
    job_manager: string;
    cache_stats: { hits: number; misses: number; hit_rate: number; backend: string };
    database: string;
    object_storage: string;
  }>('/api/health'),
  providers: () => request<{ providers: ProviderStatus[] }>('/api/providers'),
  config: () => request<Record<string, unknown>>('/api/config'),
};

// ── Maritime Intelligence (P6) ────────────────────────────────────────────────
export const chokepointsApi = {
  list: () => request<ChokepointListResponse>('/api/v1/chokepoints'),
  get: (id: string) => request<ChokepointListResponse['chokepoints'][0]>(`/api/v1/chokepoints/${id}`),
  metrics: (id: string) => request<ChokepointMetricsResponse>(`/api/v1/chokepoints/${id}/metrics`),
};

export const vesselsApi = {
  list: (params?: { sanctions_only?: boolean; dark_risk?: string; vessel_type?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.sanctions_only) q.set('sanctions_only', 'true');
    if (params?.dark_risk) q.set('dark_risk', params.dark_risk);
    if (params?.vessel_type) q.set('vessel_type', params.vessel_type);
    if (params?.limit) q.set('limit', String(params.limit));
    return request<VesselProfile[]>(`/api/v1/vessels${q.toString() ? '?' + q.toString() : ''}`);
  },
  getByMmsi: (mmsi: string) => request<VesselProfile>(`/api/v1/vessels/mmsi/${mmsi}`),
  getByImo: (imo: string) => request<VesselProfile>(`/api/v1/vessels/imo/${imo}`),
};

export const darkShipsApi = {
  list: () => request<DarkShipDetectionResponse>('/api/v1/dark-ships'),
  detect: (events: CanonicalEvent[]) =>
    request<DarkShipDetectionResponse>('/api/v1/dark-ships/detect', {
      method: 'POST',
      body: JSON.stringify({ events }),
    }),
};

export const intelApi = {
  briefing: () => request<IntelBriefing>('/api/v1/intel/briefing'),
};
