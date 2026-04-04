import { useState, useCallback } from "react";
import type { RenderMode, RenderModeConfig } from "../types/renderModes";
import { RENDER_MODE_CONFIGS } from "../types/renderModes";

const MODES: RenderMode[] = ["day", "low_light", "night_vision", "thermal"];

export function useRenderMode() {
  const [mode, setMode] = useState<RenderMode>("day");

  const cycleMode = useCallback(() => {
    setMode(current => {
      const idx = MODES.indexOf(current);
      return MODES[(idx + 1) % MODES.length];
    });
  }, []);

  const config: RenderModeConfig = RENDER_MODE_CONFIGS[mode];

  return { mode, setMode, cycleMode, config };
}
