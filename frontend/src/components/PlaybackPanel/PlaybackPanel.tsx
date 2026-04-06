import { useState, useEffect, useRef } from "react";
import { playbackApi } from "../../api/client";
import type { PlaybackQueryResponse, PlaybackFrame } from "../../api/types";
import { format } from "date-fns";

interface Props {
  aoiId: string | null;
  startTime: string;
  endTime: string;
  onFrameChange?: (frame: PlaybackFrame | null) => void;
}

const PLAYBACK_SPEED_OPTIONS = [5, 10, 15, 20, 30];

export function PlaybackPanel({ aoiId, startTime, endTime, onFrameChange }: Props) {
  const [playback, setPlayback] = useState<PlaybackQueryResponse | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(10);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function loadPlayback() {
    setLoading(true);
    try {
      const res = await playbackApi.query({
        ...(aoiId ? { aoi_id: aoiId } : {}),
        start_time: startTime,
        end_time: endTime,
        limit: 500,
      });
      setPlayback(res);
      setFrameIdx(0);
      setPlaying(false);
    } finally { setLoading(false); }
  }

  useEffect(() => {
    if (!playing || !playback) return;
    intervalRef.current = setInterval(() => {
      setFrameIdx(i => {
        const next = i + 1;
        if (next >= playback.frames.length) { setPlaying(false); return i; }
        return next;
      });
    }, 1000 / speed);
    return () => clearInterval(intervalRef.current!);
  }, [playing, speed, playback]);

  useEffect(() => {
    if (playback?.frames) {
      onFrameChange?.(playback.frames[frameIdx] ?? null);
    }
  }, [frameIdx, playback, onFrameChange]);

  const currentFrame = playback?.frames[frameIdx];

  return (
    <div className="panel" data-testid="playback-panel">
      <h3 className="panel-title">Playback</h3>
      <button className="btn btn-sm" onClick={loadPlayback} disabled={loading}>
        {loading ? "Loading…" : "Load Frames"}
      </button>
      {playback && (
        <>
          <div className="playback-controls">
            <button
              className="btn btn-sm"
              onClick={() => setFrameIdx(i => Math.max(0, i - 1))}
              disabled={frameIdx === 0}
            >⏮</button>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setPlaying(v => !v)}
            >{playing ? "⏸" : "▶"}</button>
            <button
              className="btn btn-sm"
              onClick={() => setFrameIdx(i => Math.min(playback.frames.length - 1, i + 1))}
              disabled={frameIdx >= playback.frames.length - 1}
            >⏭</button>
            <select
              className="input-sm"
              value={speed}
              onChange={e => setSpeed(Number(e.target.value))}
              title="Playback speed"
            >
              {PLAYBACK_SPEED_OPTIONS.map(s => <option key={s} value={s}>{s}×</option>)}
            </select>
          </div>
          <input
            type="range" min={0} max={playback.frames.length - 1} value={frameIdx}
            onChange={e => setFrameIdx(Number(e.target.value))}
            className="playback-scrubber"
          />
          <p className="muted">
            Frame {frameIdx + 1} / {playback.frames.length}
            {currentFrame && (() => {
              const d = new Date(currentFrame.event.event_time);
              return isNaN(d.getTime()) ? null : <> · {format(d, "MM/dd HH:mm")}</>;
            })()}
            {playback.late_arrival_count > 0 && (
              <span className="badge badge-warn"> {playback.late_arrival_count} late</span>
            )}
          </p>
        </>
      )}
    </div>
  );
}
