// TypeScript interfaces for Phase 4 sensor fusion types.
// Mirrors the backend models in src/models/sensor_fusion.py.

export interface GeoRegistration {
  lon: number;
  lat: number;
  altitude_m?: number;
  heading_deg: number;
  pitch_deg: number;
  roll_deg: number;
  fov_horizontal_deg: number;
  fov_vertical_deg: number;
  is_mobile: boolean;
}

export interface CameraInfo {
  camera_id: string;
  camera_type: string; // optical | thermal | night_vision | radar | sar
  geo_registration: GeoRegistration;
  source: string;
}

export interface CameraObservation {
  camera_id: string;
  observation_id: string;
  observed_at: string; // ISO datetime
  camera_type: string;
  geo_registration: GeoRegistration;
  clip_ref?: string;
  clip_start_offset_sec?: number;
  clip_duration_sec?: number;
  thumbnail_url?: string;
  confidence: number;
  source: string;
  provenance: string;
  tags: string[];
}

export interface MediaClipRef {
  clip_id: string;
  camera_id: string;
  recorded_at: string; // ISO datetime
  duration_sec: number;
  url: string;
  media_type: string;
  resolution_width?: number;
  resolution_height?: number;
  storage_key?: string;
  is_loopable: boolean;
  provenance: string;
}

export interface DetectionOverlay {
  detection_id: string;
  observation_id: string;
  detected_at: string;       // ISO datetime
  detection_type: string;    // vehicle | person | aircraft | vessel | infrastructure | unknown
  bounding_box?: { x: number; y: number; width: number; height: number };
  geo_location?: { lon: number; lat: number; altitude_m?: number };
  confidence: number;
  model_version?: string;
  evidence_refs: string[];
  source: string;
  provenance: string;
}
