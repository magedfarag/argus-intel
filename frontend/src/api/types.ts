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
export type SourceType =
  | 'imagery_catalog'
  | 'telemetry'
  | 'registry'
  | 'public_record'
  | 'context_feed'
  | 'derived';

export type EventType =
  | 'imagery_acquisition'
  | 'imagery_detection'
  | 'change_detection'
  | 'ship_position'
  | 'ship_track_segment'
  | 'aircraft_position'
  | 'aircraft_track_segment'
  | 'permit_event'
  | 'inspection_event'
  | 'project_event'
  | 'complaint_event'
  | 'contextual_event'
  | 'system_health_event';

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
  viewport_bbox?: [number, number, number, number]; // [west, south, east, north] EPSG:4326
  limit?: number;
}

export interface TimelineBucket {
  time: string;
  count: number;
  source: string;
}

// ── Imagery ──────────────────────────────────────────────────────────────────
export interface ImagerySearchRequest {
  geometry: GeoJsonGeometry;
  start_time: string;
  end_time: string;
  cloud_threshold?: number;
  max_results?: number;
  connectors?: string[];
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
  viewport_bbox?: [number, number, number, number]; // [west, south, east, north] EPSG:4326
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

// ── Maritime Intelligence (P6) ────────────────────────────────────────────────

export type ThreatLabel = 'LOW' | 'MODERATE' | 'ELEVATED' | 'HIGH' | 'CRITICAL';

export interface ChokepointMetric {
  date: string;
  daily_flow_mbbl: number;
  vessel_count: number;
  threat_level: number;
}

export interface Chokepoint {
  id: string;
  name: string;
  controlling_nation: string;
  geometry: GeoJsonGeometry;
  centroid: { lon: number; lat: number };
  daily_flow_mbbl: number;
  vessel_count_24h: number;
  threat_level: number;
  threat_label: ThreatLabel;
  trend: '+' | '-' | '=';
  description: string;
}

export interface ChokepointListResponse {
  chokepoints: Chokepoint[];
}

export interface ChokepointMetricsResponse {
  chokepoint_id: string;
  name: string;
  metrics: ChokepointMetric[];
}

export type SanctionsStatus =
  | 'clean'
  | 'OFAC-SDN'
  | 'UN-sanctioned'
  | 'EU-sanctioned'
  | 'shadow-fleet'
  | 'watch-list';

export interface VesselProfile {
  imo: string;
  mmsi: string;
  name: string;
  flag: string;
  flag_emoji: string;
  vessel_type: string;
  gross_tonnage: number;
  year_built: number;
  owner: string;
  operator: string;
  sanctions_status: SanctionsStatus;
  sanctions_detail?: string;
  dark_ship_risk: string;
  last_known_port: string;
  notes?: string;
}

export interface DarkShipCandidate {
  mmsi: string;
  vessel_name: string;
  gap_start: string;
  gap_end: string;
  gap_hours: number;
  last_known_lon: number;
  last_known_lat: number;
  reappear_lon?: number;
  reappear_lat?: number;
  position_jump_km?: number;
  sanctions_flag: boolean;
  dark_ship_risk: string;
  confidence: number;
  event_id: string;
}

export interface DarkShipDetectionResponse {
  candidates: DarkShipCandidate[];
  total: number;
  events_analysed: number;
}

export interface VesselAlert {
  mmsi: string;
  vessel_name: string;
  sanctions_status: string;
  alert_type: 'dark_ship' | 'sanctions_entry' | 'position_jump';
  detail: string;
  confidence: number;
}

export interface IntelBriefing {
  briefing_id: string;
  timestamp: string;
  classification: string;
  risk_level: 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW';
  risk_color: string;
  executive_summary: string;
  key_findings: string[];
  vessel_alerts: VesselAlert[];
  chokepoint_status: Array<{
    id: string;
    name: string;
    threat_level: number;
    threat_label: string;
    daily_flow_mbbl: number;
    trend: string;
  }>;
  dark_ship_count: number;
  sanctioned_vessel_count: number;
  active_vessel_count: number;
}
