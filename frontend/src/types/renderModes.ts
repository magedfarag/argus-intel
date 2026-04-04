export type RenderMode = "day" | "low_light" | "night_vision" | "thermal";

export interface RenderModeConfig {
  mode: RenderMode;
  label: string;
  description: string;
  /** CSS filter string applied to the map canvas container */
  cssFilter: string;
  /** Tint color applied as a semi-transparent overlay */
  tintColor?: string;
  tintOpacity?: number;
}

export const RENDER_MODE_CONFIGS: Record<RenderMode, RenderModeConfig> = {
  day: {
    mode: "day",
    label: "Day",
    description: "Standard daylight visualization",
    cssFilter: "none",
  },
  low_light: {
    mode: "low_light",
    label: "Low Light",
    description: "Reduced brightness, enhanced contrast for dusk/dawn operations",
    cssFilter: "brightness(0.65) contrast(1.2) saturate(0.8)",
    tintColor: "#001133",
    tintOpacity: 0.3,
  },
  night_vision: {
    mode: "night_vision",
    label: "Night Vision",
    description: "Green-channel amplification simulation for NVG operations",
    cssFilter:
      "brightness(0.3) contrast(1.5) saturate(0) sepia(1) hue-rotate(80deg) brightness(2.5)",
    tintColor: "#004400",
    tintOpacity: 0.4,
  },
  thermal: {
    mode: "thermal",
    label: "Thermal",
    description:
      "False-color thermal IR simulation — heat sources appear warm-white to red",
    cssFilter:
      "brightness(0.4) contrast(2.0) saturate(0) sepia(1) hue-rotate(320deg) invert(1) brightness(1.8)",
    tintColor: "#200010",
    tintOpacity: 0.35,
  },
};
