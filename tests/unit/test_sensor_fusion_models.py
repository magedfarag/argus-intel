"""Unit tests for Phase 4 sensor-fusion Pydantic models.

Covers:
- GeoRegistration
- CameraObservation (including UTC validator)
- MediaClipRef
- RenderModeEvent
- DetectionOverlay (including parametrized confidence and detection_type)
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.models.sensor_fusion import (
    CameraObservation,
    DetectionOverlay,
    GeoRegistration,
    MediaClipRef,
    RenderModeEvent,
)

_NOW = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
_GEO = GeoRegistration(lon=56.416, lat=26.594)


# ── GeoRegistration ───────────────────────────────────────────────────────────


class TestGeoRegistration:
    def test_geo_registration_valid_minimal(self):
        geo = GeoRegistration(lon=0.0, lat=0.0)
        assert geo.lon == 0.0
        assert geo.lat == 0.0

    def test_geo_registration_full_fields(self):
        geo = GeoRegistration(
            lon=56.416,
            lat=26.594,
            altitude_m=45.0,
            heading_deg=270.0,
            pitch_deg=-10.0,
            roll_deg=2.5,
            fov_horizontal_deg=80.0,
            fov_vertical_deg=50.0,
            is_mobile=False,
        )
        assert geo.altitude_m == 45.0
        assert geo.is_mobile is False
        assert geo.roll_deg == 2.5

    def test_geo_registration_heading_field(self):
        geo = GeoRegistration(lon=10.0, lat=20.0, heading_deg=90.0)
        assert geo.heading_deg == 90.0

    def test_geo_registration_is_mobile_default_false(self):
        geo = GeoRegistration(lon=0.0, lat=0.0)
        assert geo.is_mobile is False

    def test_geo_registration_is_mobile_true(self):
        geo = GeoRegistration(lon=32.15, lat=43.22, altitude_m=500.0, is_mobile=True)
        assert geo.is_mobile is True


# ── CameraObservation ─────────────────────────────────────────────────────────


class TestCameraObservation:
    def test_camera_observation_valid(self):
        obs = CameraObservation(
            camera_id="cam-test-01",
            observation_id="obs-test-001",
            observed_at="2026-04-04T12:00:00Z",
            geo_registration=_GEO,
            confidence=0.85,
            source="argus-demo",
            provenance="unit-test",
        )
        assert obs.confidence == 0.85
        assert obs.observed_at.tzinfo is not None

    def test_camera_observation_utc_required(self):
        with pytest.raises(ValidationError):
            CameraObservation(
                camera_id="cam-test-01",
                observation_id="obs-test-002",
                observed_at=datetime(2026, 4, 4, 12, 0, 0),  # naive — no tzinfo
                geo_registration=_GEO,
                source="argus-demo",
                provenance="unit-test",
            )

    def test_camera_observation_source_present(self):
        obs = CameraObservation(
            camera_id="cam-test-01",
            observation_id="obs-test-003",
            observed_at=_NOW,
            geo_registration=_GEO,
            source="argus-cctv-hormuz",
            provenance="unit-test",
        )
        assert obs.source != ""

    def test_camera_observation_tags_list(self):
        obs = CameraObservation(
            camera_id="cam-test-01",
            observation_id="obs-test-004",
            observed_at=_NOW,
            geo_registration=_GEO,
            source="argus-demo",
            provenance="unit-test",
            tags=["alpha", "beta", "gamma"],
        )
        assert isinstance(obs.tags, list)
        assert obs.tags == ["alpha", "beta", "gamma"]

    def test_camera_observation_optional_clip_fields(self):
        obs = CameraObservation(
            camera_id="cam-test-01",
            observation_id="obs-test-005",
            observed_at=_NOW,
            geo_registration=_GEO,
            source="argus-demo",
            provenance="unit-test",
        )
        assert obs.clip_ref is None
        assert obs.thumbnail_url is None

    def test_camera_observation_confidence_default_one(self):
        obs = CameraObservation(
            camera_id="cam-test-01",
            observation_id="obs-test-006",
            observed_at=_NOW,
            geo_registration=_GEO,
            source="argus-demo",
            provenance="unit-test",
        )
        assert obs.confidence == 1.0


# ── MediaClipRef ──────────────────────────────────────────────────────────────


class TestMediaClipRef:
    def test_media_clip_valid(self):
        clip = MediaClipRef(
            clip_id="clip-001",
            camera_id="cam-test-01",
            recorded_at=_NOW,
            duration_sec=120.0,
            url="/demo/clips/test.mp4",
            provenance="unit-test",
        )
        assert clip.clip_id == "clip-001"
        assert clip.camera_id == "cam-test-01"

    def test_media_clip_is_loopable_default_false(self):
        # Model default for is_loopable is False; demo seed explicitly sets True
        clip = MediaClipRef(
            clip_id="clip-002",
            camera_id="cam-test-01",
            recorded_at=_NOW,
            duration_sec=60.0,
            url="/demo/clips/test2.mp4",
            provenance="unit-test",
        )
        assert clip.is_loopable is False

    def test_media_clip_url_present(self):
        clip = MediaClipRef(
            clip_id="clip-003",
            camera_id="cam-test-01",
            recorded_at=_NOW,
            duration_sec=30.0,
            url="/demo/clips/test3.mp4",
            provenance="unit-test",
        )
        assert clip.url != ""

    def test_media_clip_duration_positive(self):
        clip = MediaClipRef(
            clip_id="clip-004",
            camera_id="cam-test-01",
            recorded_at=_NOW,
            duration_sec=300.0,
            url="/demo/clips/test4.mp4",
            provenance="unit-test",
        )
        assert clip.duration_sec > 0

    def test_media_clip_utc_recorded_at_required(self):
        with pytest.raises(ValidationError):
            MediaClipRef(
                clip_id="clip-005",
                camera_id="cam-test-01",
                recorded_at=datetime(2026, 4, 4, 12, 0, 0),  # naive
                duration_sec=60.0,
                url="/demo/clips/test5.mp4",
                provenance="unit-test",
            )


# ── RenderModeEvent ───────────────────────────────────────────────────────────


class TestRenderModeEvent:
    def test_render_mode_event_valid(self):
        evt = RenderModeEvent(
            event_id="rme-001",
            occurred_at=_NOW,
            from_mode="day",
            to_mode="night_vision",
            triggered_by="user",
        )
        assert evt.from_mode == "day"
        assert evt.to_mode == "night_vision"
        assert evt.triggered_by == "user"

    def test_render_mode_event_triggered_by_default(self):
        evt = RenderModeEvent(
            event_id="rme-002",
            occurred_at=_NOW,
            from_mode="low_light",
            to_mode="thermal",
        )
        assert evt.triggered_by == "user"

    def test_render_mode_event_utc_required(self):
        with pytest.raises(ValidationError):
            RenderModeEvent(
                event_id="rme-003",
                occurred_at=datetime(2026, 4, 4, 12, 0, 0),  # naive
                from_mode="day",
                to_mode="thermal",
            )


# ── DetectionOverlay ──────────────────────────────────────────────────────────


class TestDetectionOverlay:
    def test_detection_overlay_valid_no_location(self):
        det = DetectionOverlay(
            detection_id="det-test-001",
            observation_id="obs-test-001",
            detected_at=_NOW,
            detection_type="vehicle",
            bounding_box={"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.1},
            source="test-source",
            provenance="unit-test",
        )
        assert det.geo_location is None
        assert det.bounding_box is not None

    def test_detection_overlay_valid_with_location(self):
        det = DetectionOverlay(
            detection_id="det-test-002",
            observation_id="obs-test-001",
            detected_at=_NOW,
            detection_type="vessel",
            bounding_box={"x": 0.3, "y": 0.4, "width": 0.2, "height": 0.15},
            geo_location={"lon": 56.42, "lat": 26.60, "altitude_m": 0.0},
            source="test-source",
            provenance="unit-test",
        )
        assert det.geo_location["lon"] == pytest.approx(56.42)
        assert det.geo_location["lat"] == pytest.approx(26.60)

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_detection_overlay_confidence_range(self, confidence: float):
        det = DetectionOverlay(
            detection_id=f"det-test-conf-{confidence}",
            observation_id="obs-test-001",
            detected_at=_NOW,
            detection_type="vehicle",
            source="test",
            provenance="unit-test",
            confidence=confidence,
        )
        assert det.confidence == pytest.approx(confidence)

    @pytest.mark.parametrize(
        "dtype",
        ["vehicle", "vessel", "aircraft", "infrastructure", "person", "unknown"],
    )
    def test_detection_overlay_detection_types(self, dtype: str):
        det = DetectionOverlay(
            detection_id=f"det-test-{dtype}",
            observation_id="obs-test-001",
            detected_at=_NOW,
            detection_type=dtype,
            source="test",
            provenance="unit-test",
        )
        assert det.detection_type == dtype

    def test_detection_overlay_evidence_refs_list(self):
        det = DetectionOverlay(
            detection_id="det-test-003",
            observation_id="obs-test-001",
            detected_at=_NOW,
            detection_type="person",
            source="test",
            provenance="unit-test",
            evidence_refs=["ev-001", "ev-002"],
        )
        assert isinstance(det.evidence_refs, list)
        assert det.evidence_refs == ["ev-001", "ev-002"]

    def test_detection_overlay_evidence_refs_default_empty(self):
        det = DetectionOverlay(
            detection_id="det-test-004",
            observation_id="obs-test-001",
            detected_at=_NOW,
            detection_type="unknown",
            source="test",
            provenance="unit-test",
        )
        assert det.evidence_refs == []

    def test_detection_overlay_utc_required(self):
        with pytest.raises(ValidationError):
            DetectionOverlay(
                detection_id="det-test-005",
                observation_id="obs-test-001",
                detected_at=datetime(2026, 4, 4, 12, 0, 0),  # naive
                detection_type="vehicle",
                source="test",
                provenance="unit-test",
            )
