// React hooks for Phase 4 camera feed data.
// Each hook uses AbortController for cleanup on unmount.

import { useEffect, useState } from 'react';
import { fetchCameras, fetchCameraObservations, fetchCameraClips, fetchDetections } from '../api/cameraApi';
import type { CameraInfo, CameraObservation, MediaClipRef, DetectionOverlay } from '../types/sensorFusion';

// ── Camera list ───────────────────────────────────────────────────────────────

export function useCameras(): {
  cameras: CameraInfo[];
  loading: boolean;
  error: string | null;
} {
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchCameras(controller.signal)
      .then(setCameras)
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, []);

  return { cameras, loading, error };
}

// ── Camera observations + clips ───────────────────────────────────────────────

export function useCameraObservations(
  cameraId: string | null,
  start?: string,
  end?: string,
): {
  observations: CameraObservation[];
  clips: MediaClipRef[];
  loading: boolean;
} {
  const [observations, setObservations] = useState<CameraObservation[]>([]);
  const [clips, setClips] = useState<MediaClipRef[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!cameraId) {
      setObservations([]);
      setClips([]);
      return;
    }

    const controller = new AbortController();
    setLoading(true);

    const params = { start, end };

    Promise.all([
      fetchCameraObservations(cameraId, params, controller.signal),
      fetchCameraClips(cameraId, params, controller.signal),
    ])
      .then(([obs, cl]) => {
        setObservations(obs);
        setClips(cl);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          setObservations([]);
          setClips([]);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [cameraId, start, end]);

  return { observations, clips, loading };
}

// ── Detection overlay layer ───────────────────────────────────────────────────

export function useDetectionLayer(
  confidenceMin?: number,
  detectionType?: string,
): {
  detections: DetectionOverlay[];
  loading: boolean;
} {
  const [detections, setDetections] = useState<DetectionOverlay[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    fetchDetections(
      { confidence_min: confidenceMin, detection_type: detectionType },
      controller.signal,
    )
      .then(setDetections)
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          console.error('[useDetectionLayer]', err);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [confidenceMin, detectionType]);

  return { detections, loading };
}
