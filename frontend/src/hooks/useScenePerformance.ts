import { useEffect, useRef, useState } from "react";

export interface PerformanceReport {
  fps: number;
  frameMs: number;
  entityCount: number;
  /** True when entityCount > 500 — triggers automatic quality throttling. */
  isDenseView: boolean;
  /** Alias for isDenseView — use to switch to simplified rendering. */
  shouldReduceDetail: boolean;
}

const DENSE_THRESHOLD = 500;
const SAMPLE_WINDOW_MS = 500;

export function useScenePerformance(entityCount: number): PerformanceReport {
  const [fps, setFps] = useState(60);
  const [frameMs, setFrameMs] = useState(16);

  const frameCountRef = useRef(0);
  const lastTimeRef = useRef(performance.now());
  const rafIdRef = useRef<number | null>(null);

  useEffect(() => {
    function tick(): void {
      const now = performance.now();
      frameCountRef.current++;
      const elapsed = now - lastTimeRef.current;

      if (elapsed >= SAMPLE_WINDOW_MS) {
        const measuredFps = Math.round((frameCountRef.current / elapsed) * 1000);
        const measuredFrameMs = Math.round(elapsed / frameCountRef.current);
        setFps(measuredFps);
        setFrameMs(measuredFrameMs);
        frameCountRef.current = 0;
        lastTimeRef.current = now;
      }

      rafIdRef.current = requestAnimationFrame(tick);
    }

    rafIdRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, []);

  const isDenseView = entityCount > DENSE_THRESHOLD;
  return { fps, frameMs, entityCount, isDenseView, shouldReduceDetail: isDenseView };
}
