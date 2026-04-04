// TypeScript interfaces for Phase 5 investigation workflow data.
// Mirrors backend Pydantic models in app/routers/investigations.py.

export type InvestigationStatus = 'draft' | 'active' | 'archived' | 'closed';
export type WatchlistEntryType = 'vessel' | 'aircraft' | 'location' | 'event_pattern' | 'person';

export interface WatchlistEntry {
  id: string;
  entry_type: WatchlistEntryType;
  identifier: string;
  label?: string;
  notes?: string;
  added_at: string;
  confidence?: number;
}

export interface InvestigationNote {
  id: string;
  investigation_id: string;
  content: string;
  author?: string;
  created_at: string;
  tags: string[];
}

export interface EvidenceLink {
  evidence_id: string;
  source: string;
  url?: string;
  description?: string;
}

export interface Investigation {
  id: string;
  name: string;
  description?: string;
  status: InvestigationStatus;
  created_at: string;
  updated_at: string;
  created_by?: string;
  tags: string[];
  watchlist: WatchlistEntry[];
  notes: InvestigationNote[];
  evidence_links: EvidenceLink[];
  linked_event_ids: string[];
}

export interface InvestigationCreateRequest {
  name: string;
  description?: string;
  created_by?: string;
  tags?: string[];
}

// ── Absence Detection ──────────────────────────────────────────────────────────

export type AbsenceSignalType =
  | 'ais_gap'
  | 'gps_denial'
  | 'camera_silence'
  | 'expected_missing'
  | 'comm_blackout'
  | 'track_termination';

export type AbsenceSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface AbsenceSignal {
  signal_id: string;
  signal_type: AbsenceSignalType;
  entity_id?: string;
  entity_type?: string;
  gap_start: string;
  gap_end?: string;
  severity: AbsenceSeverity;
  confidence: number;
  detection_method: string;
  notes?: string;
  resolved: boolean;
}

export interface AbsenceAlert {
  alert_id: string;
  title: string;
  signals: string[];
  severity: AbsenceSeverity;
  area_description?: string;
  created_at: string;
  confidence: number;
}
