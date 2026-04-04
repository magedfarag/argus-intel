// TypeScript interfaces for Phase 2 operational layer data.
// Mirrors backend Pydantic models in src/models/operational_layers.py.

export interface SatelliteOrbit {
  satellite_id: string;
  norad_id?: number;
  tle_line1?: string;
  tle_line2?: string;
  orbital_period_minutes?: number;
  inclination_deg?: number;
  altitude_km?: number;
  source: string;
  loaded_at: string; // ISO datetime
}

export interface SatellitePass {
  satellite_id: string;
  norad_id?: number;
  aos: string; // ISO datetime — Acquisition of Signal
  los: string; // ISO datetime — Loss of Signal
  max_elevation_deg?: number;
  footprint_geojson?: object;
  sensor_type?: string;
  confidence: number;
  source: string;
}

export interface AirspaceRestriction {
  restriction_id: string;
  name: string;
  restriction_type: string;
  geometry_geojson: object;
  lower_limit_ft?: number;
  upper_limit_ft?: number;
  valid_from: string;
  valid_to?: string;
  is_active: boolean;
  source: string;
  provenance?: string;
}

export interface NotamEvent {
  notam_id: string;
  notam_number: string;
  subject: string;
  condition: string;
  location_icao?: string;
  effective_from: string;
  effective_to?: string;
  geometry_geojson?: object;
  raw_text?: string;
  source: string;
}

export interface GpsJammingEvent {
  jamming_id: string;
  detected_at: string;
  location_lon: number;
  location_lat: number;
  radius_km?: number;
  affected_area_geojson?: object;
  jamming_type: string;
  signal_strength_db?: number;
  confidence: number;
  source: string;
  provenance: string;
  detection_method: string;
}

export interface StrikeEvent {
  strike_id: string;
  occurred_at: string;
  location_lon: number;
  location_lat: number;
  location_geojson?: object;
  strike_type: string;
  target_description?: string;
  damage_severity?: string;
  confidence: number;
  evidence_refs: string[];
  source: string;
  provenance: string;
  corroboration_count: number;
}

export interface HeatmapPoint {
  lon: number;
  lat: number;
  weight: number;
}
