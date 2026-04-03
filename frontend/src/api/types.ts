// Shared API types — mirrors backend Pydantic models

export interface GeoJsonGeometry {
  type: 'Polygon' | 'MultiPolygon' | 'Point';
  coordinates: unknown[];
}

// ── AOIs ────────────────────────────────────────────────────────────────────
export interface Aoi {
  id: string;
  name: string;
  geometry: GeoJsonGeometry;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}
export interface CreateAoiRequest {
  name: string;
  geometry: GeoJsonGeometry;
  metadata?: Record<string, unknown>;
}

// ── Events ───────────────────────────────────────────────────────────────────
export type SourceType = 'imagery' | 'telemetry' | 'context' | 'permit';
export type EventType =
  | 'imagery_acquisition'
  | 'ship_position'
  | 'aircraft_position'
  | 'contextual_event'
  | 'permit';

export interface CanonicalEvent {
  event_id: string;
  event_time: string;
  ingested_at: string;
  source: string;
  source_type: SourceType;
  event_type: EventType;
  entity_id?: string;
  geometry?: GeoJsonGeometry;
  confidence?: number;
  quality_flags: string[];
  attributes?: Record<string, unknown>;
}

export interface EventSearchRequest {
  aoi_id?: string;
  geometry?: GeoJsonGeometry;
  start_time: string;
  end_time: string;
  source_types?: SourceType[];
  event_types?: EventType[];
  limit?: number;
}

export interface TimelineBucket {
  time: string;
  count: number;
  source: string;
}

// ── Imagery ──────────────────────────────────────────────────────────────────
export interface ImagerySearchRequest {
  aoi_id?: string;
  geometry?: GeoJsonGeometry;
  start_date: string;
  end_date: string;
  max_cloud_cover?: number;
  collections?: string[];
}

export interface ImageryItem {
  item_id: string;
  collection: string;
  provider: string;
  datetime: string;
  cloud_cover?: number;
  geometry: GeoJsonGeometry;
  thumbnail_url?: string;
}

// ── Analytics ────────────────────────────────────────────────────────────────
export type ChangeClass = 'new_construction' | 'demolition' | 'land_clearing' | 'no_change';
export type ReviewDecision = 'confirmed' | 'dismissed';

export interface ChangeCandidate {
  candidate_id: string;
  job_id: string;
  aoi_id: string;
  change_class: ChangeClass;
  confidence: number;
  ndvi_delta?: number;
  rationale: string;
  review_status: 'pending' | 'confirmed' | 'dismissed';
  reviewed_at?: string;
  analyst_id?: string;
  analyst_notes?: string;
}

export interface ChangeDetectionJob {
  job_id: string;
  aoi_id: string;
  state: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  completed_at?: string;
  candidate_count?: number;
  error?: string;
}

// ── Exports ──────────────────────────────────────────────────────────────────
export interface ExportRequest {
  aoi_id?: string;
  start_time: string;
  end_time: string;
  format: 'csv' | 'geojson';
  include_restricted?: boolean;
}

export interface ExportJob {
  job_id: string;
  state: 'pending' | 'running' | 'completed' | 'failed';
  download_url?: string;
  row_count?: number;
}

// ── Playback ─────────────────────────────────────────────────────────────────
export interface PlaybackQueryRequest {
  aoi_id?: string;
  geometry?: GeoJsonGeometry;
  start_time: string;
  end_time: string;
  source_types?: SourceType[];
  include_late_arrivals?: boolean;
  limit?: number;
}

export interface PlaybackFrame {
  sequence: number;
  event: CanonicalEvent;
  is_late_arrival: boolean;
}

export interface PlaybackQueryResponse {
  frames: PlaybackFrame[];
  late_arrival_count: number;
  sources_included: string[];
}

// ── Provider / Config ─────────────────────────────────────────────────────────
export interface ProviderStatus {
  name: string;
  available: boolean;
  mode?: string;
}

// ── Health Dashboard (P5-3.1, P5-3.5) ────────────────────────────────────────
export interface SourceHealthRecord {
  connector_id: string;
  display_name: string;
  source_type: string;
  is_healthy: boolean;
  last_successful_poll?: string;
  last_error_at?: string;
  last_error_message?: string;
  consecutive_errors: number;
  total_requests: number;
  total_errors: number;
  freshness_status: 'fresh' | 'stale' | 'critical' | 'unknown';
  freshness_age_minutes?: number;
  requests_last_hour: number;
}

export interface HealthAlert {
  alert_id: string;
  connector_id: string;
  severity: 'warning' | 'critical';
  message: string;
  triggered_at: string;
  resolved: boolean;
  resolved_at?: string;
}

export interface HealthDashboardResponse {
  connectors: SourceHealthRecord[];
  alerts: HealthAlert[];
  overall_healthy: boolean;
  generated_at: string;
  total_requests_last_hour: number;
  total_errors_last_hour: number;
}

export interface UsagePeriod {
  connector_id: string;
  period_start: string;
  period_end: string;
  request_count: number;
  error_count: number;
  is_paid: boolean;
}
