// API client for Phase 4 camera feed endpoints.
// Follows the same fetch + x-api-key pattern as operationalLayersApi.ts.

import { getApiKey } from './client';
import type { CameraInfo, CameraObservation, MediaClipRef, DetectionOverlay } from '../types/sensorFusion';

const BASE = '';

async function camRequest<T>(
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

// ── Cameras ───────────────────────────────────────────────────────────────────

export function fetchCameras(signal?: AbortSignal): Promise<CameraInfo[]> {
  return camRequest<CameraInfo[]>('/api/v1/cameras', signal);
}

export function fetchCamera(cameraId: string, signal?: AbortSignal): Promise<CameraInfo> {
  return camRequest<CameraInfo>(`/api/v1/cameras/${encodeURIComponent(cameraId)}`, signal);
}

export function fetchCameraObservations(
  cameraId: string,
  params?: { start?: string; end?: string; limit?: number },
  signal?: AbortSignal,
): Promise<CameraObservation[]> {
  const qs = new URLSearchParams();
  if (params?.start) qs.set('start', params.start);
  if (params?.end) qs.set('end', params.end);
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const query = qs.toString() ? `?${qs}` : '';
  return camRequest<CameraObservation[]>(
    `/api/v1/cameras/${encodeURIComponent(cameraId)}/observations${query}`,
    signal,
  );
}

export function fetchCameraClips(
  cameraId: string,
  params?: { start?: string; end?: string },
  signal?: AbortSignal,
): Promise<MediaClipRef[]> {
  const qs = new URLSearchParams();
  if (params?.start) qs.set('start', params.start);
  if (params?.end) qs.set('end', params.end);
  const query = qs.toString() ? `?${qs}` : '';
  return camRequest<MediaClipRef[]>(
    `/api/v1/cameras/${encodeURIComponent(cameraId)}/clips${query}`,
    signal,
  );
}

// ── Detections ────────────────────────────────────────────────────────────────

export function fetchDetections(
  params?: {
    detection_type?: string;
    confidence_min?: number;
    observation_id?: string;
  },
  signal?: AbortSignal,
): Promise<DetectionOverlay[]> {
  const qs = new URLSearchParams();
  if (params?.detection_type) qs.set('detection_type', params.detection_type);
  if (params?.confidence_min !== undefined) qs.set('confidence_min', String(params.confidence_min));
  if (params?.observation_id) qs.set('observation_id', params.observation_id);
  const query = qs.toString() ? `?${qs}` : '';
  return camRequest<DetectionOverlay[]>(`/api/v1/detections${query}`, signal);
}
