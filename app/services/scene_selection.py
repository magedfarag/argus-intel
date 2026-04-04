"""Scene ranking and pair selection for change detection.

Scoring formula (weights confirmed to sum to 1.0):
  score = (1 - cloud_fraction) * 0.40
        + recency_score        * 0.35
        + aoi_overlap          * 0.25

recency_score is 1.0 for today, 0.0 for the oldest day in the window.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from app.models.scene import SceneMetadata


def _recency_score(scene: SceneMetadata, newest_dt: datetime, oldest_dt: datetime) -> float:
    span = (newest_dt - oldest_dt).total_seconds()
    if span <= 0:
        return 1.0
    age  = (newest_dt - scene.acquired_at).total_seconds()
    return max(0.0, 1.0 - age / span)


def rank_scenes(scenes: List[SceneMetadata]) -> List[SceneMetadata]:
    """Return *scenes* sorted by composite quality score, best first."""
    if not scenes:
        return []
    dates     = [s.acquired_at for s in scenes]
    newest_dt = max(dates)
    oldest_dt = min(dates)

    def score(s: SceneMetadata) -> float:
        cloud_penalty = (100.0 - s.cloud_cover) / 100.0
        recency       = _recency_score(s, newest_dt, oldest_dt)
        overlap       = s.aoi_overlap
        return cloud_penalty * 0.40 + recency * 0.35 + overlap * 0.25

    return sorted(scenes, key=score, reverse=True)


def select_scene_pair(
    ranked: List[SceneMetadata],
    min_temporal_gap_days: int = 7,
) -> Tuple[Optional[SceneMetadata], Optional[SceneMetadata]]:
    """Pick (before, after) scene pair for change detection.

    Strategy:
      - *after* is the highest-ranked (most recent, low cloud) scene.
      - *before* is the highest-ranked scene that is at least
        *min_temporal_gap_days* older than *after*.

    Returns (None, None) if fewer than 2 scenes are available.
    """
    if len(ranked) < 2:
        return None, None

    after  = ranked[0]
    before = None
    for candidate in ranked[1:]:
        gap = (after.acquired_at - candidate.acquired_at).days
        if gap >= min_temporal_gap_days:
            before = candidate
            break

    if before is None:
        # No gap constraint satisfied; use the oldest available scene.
        before = ranked[-1]

    return before, after
