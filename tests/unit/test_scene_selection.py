"""Unit tests for scene_selection service."""
from __future__ import annotations
from datetime import datetime, timedelta
from app.models.scene import SceneMetadata
from app.services.scene_selection import rank_scenes, select_scene_pair

def _s(sid, cloud=5.0, days_ago=0):
    return SceneMetadata(scene_id=sid, provider="sentinel2", satellite="S2",
        acquired_at=datetime(2026, 3, 28) - timedelta(days=days_ago),
        cloud_cover=cloud, bbox=[0, 0, 1, 1], aoi_overlap=1.0)

def test_rank_scenes_empty():
    assert rank_scenes([]) == []

def test_rank_prefers_low_cloud():
    ranked = rank_scenes([_s("hi", cloud=50, days_ago=1), _s("lo", cloud=5, days_ago=1)])
    assert ranked[0].scene_id == "lo"

def test_rank_prefers_recent():
    ranked = rank_scenes([_s("old", days_ago=20), _s("new", days_ago=1)])
    assert ranked[0].scene_id == "new"

def test_select_pair_single_returns_none():
    b, a = select_scene_pair([_s("only")])
    assert b is None and a is None

def test_select_pair_after_is_newest():
    ranked = rank_scenes([_s("old", days_ago=20), _s("new", days_ago=1)])
    b, a = select_scene_pair(ranked)
    assert a.scene_id == "new" and b.scene_id == "old"

def test_select_pair_fallback_on_no_gap():
    ranked = rank_scenes([_s("a", days_ago=1), _s("b", days_ago=2)])
    b, a = select_scene_pair(ranked, min_temporal_gap_days=30)
    assert b.scene_id == "b"
