import type { RenderMode } from "../../types/renderModes";
import { RENDER_MODE_CONFIGS } from "../../types/renderModes";

const MODE_DOTS: Record<RenderMode, string> = {
  day: "#f5c842",
  low_light: "#ff8c42",
  night_vision: "#00ff44",
  thermal: "#ff4422",
};

const MODES: RenderMode[] = ["day", "low_light", "night_vision", "thermal"];

interface Props {
  mode: RenderMode;
  onModeChange: (mode: RenderMode) => void;
}

export function RenderModeSelector({ mode, onModeChange }: Props) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        gap: 4,
        background: "rgba(8,16,30,0.82)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 6,
        padding: "3px 5px",
        pointerEvents: "auto",
      }}
      title="Scene render mode"
    >
      {MODES.map(m => {
        const cfg = RENDER_MODE_CONFIGS[m];
        const isActive = m === mode;
        return (
          <button
            key={m}
            onClick={() => onModeChange(m)}
            title={cfg.description}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              background: isActive ? "rgba(255,255,255,0.12)" : "transparent",
              border: isActive
                ? `1px solid ${MODE_DOTS[m]}`
                : "1px solid transparent",
              borderRadius: 4,
              color: isActive ? "#f8fafc" : "#94a3b8",
              cursor: "pointer",
              fontSize: 11,
              fontFamily: "monospace",
              fontWeight: isActive ? 700 : 400,
              padding: "2px 7px",
              transition: "background 0.15s, border-color 0.15s, color 0.15s",
              whiteSpace: "nowrap",
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: MODE_DOTS[m],
                flexShrink: 0,
                boxShadow: isActive ? `0 0 5px ${MODE_DOTS[m]}` : "none",
              }}
            />
            {cfg.label.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}
