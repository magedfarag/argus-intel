"""Camera feed and clip router — Phase 4, Track B.

GET  /api/v1/cameras                          — list all cameras with geo_registration
GET  /api/v1/cameras/detections               — list detection overlays (query: detection_type, confidence_min)
GET  /api/v1/cameras/{camera_id}              — single camera detail
GET  /api/v1/cameras/{camera_id}/observations — list observations for a camera
     query: start, end (ISO datetime), limit=50
GET  /api/v1/cameras/{camera_id}/clips        — list clips for a camera
     query: start, end
POST /api/v1/cameras/{camera_id}/observations — register a new camera observation

In-memory stores are seeded at module load with 3 cameras — a fixed CCTV at
the Strait of Hormuz, a drone over the Black Sea, and a thermal-radar station
at the Baltic — each with representative observations and 1-2 clip references.

IMPORTANT — route order: /detections is registered BEFORE /{camera_id} so that
GET /api/v1/cameras/detections is not captured by the path-parameter route.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.models.sensor_fusion import (
    CameraObservation,
    DetectionOverlay,
    GeoRegistration,
    MediaClipRef,
)

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])

# ── In-memory stores ──────────────────────────────────────────────────────────

# camera_id → GeoRegistration (the authoritative world anchor for each camera)
_camera_store: Dict[str, GeoRegistration] = {}

# camera_id → camera type and display metadata
_camera_meta: Dict[str, Dict] = {}

# observation_id → CameraObservation
_observation_store: Dict[str, CameraObservation] = {}

# clip_id → MediaClipRef
_clip_store: Dict[str, MediaClipRef] = {}

# detection_id → DetectionOverlay  (shared with detections router)
_detection_store: Dict[str, DetectionOverlay] = {}

_REF_NOW = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)


# ── Seed data ─────────────────────────────────────────────────────────────────


def _seed() -> None:
    # ── Camera 1: Fixed CCTV at Strait of Hormuz ─────────────────────────────
    georeg_hormuz = GeoRegistration(
        lon=56.416,
        lat=26.594,
        altitude_m=45.0,
        heading_deg=270.0,
        pitch_deg=-10.0,
        fov_horizontal_deg=80.0,
        fov_vertical_deg=50.0,
        is_mobile=False,
    )
    _camera_store["cam-hormuz-01"] = georeg_hormuz
    _camera_meta["cam-hormuz-01"] = {
        "camera_id": "cam-hormuz-01",
        "camera_type": "optical",
        "label": "Hormuz CCTV — coastal fixed",
        "geo_registration": georeg_hormuz,
    }

    obs1 = CameraObservation(
        camera_id="cam-hormuz-01",
        observation_id="obs-hormuz-01-001",
        observed_at=_REF_NOW - timedelta(hours=6),
        camera_type="optical",
        geo_registration=georeg_hormuz,
        clip_ref="/demo/clips/clip-hormuz-01.mp4",
        clip_start_offset_sec=0.0,
        clip_duration_sec=300.0,
        thumbnail_url="/demo/clips/clip-hormuz-01-thumb.jpg",
        confidence=0.97,
        source="argus-cctv-hormuz",
        provenance="demo-seed",
        tags=["strait", "vessel-traffic", "hormuz"],
    )
    _observation_store[obs1.observation_id] = obs1

    _clip_store["clip-hormuz-01"] = MediaClipRef(
        clip_id="clip-hormuz-01",
        camera_id="cam-hormuz-01",
        recorded_at=_REF_NOW - timedelta(hours=6),
        duration_sec=300.0,
        url="/demo/clips/clip-hormuz-01.mp4",
        media_type="video/mp4",
        resolution_width=1920,
        resolution_height=1080,
        storage_key="demo/clips/clip-hormuz-01.mp4",
        is_loopable=True,
        provenance="demo-seed",
    )
    _clip_store["clip-hormuz-02"] = MediaClipRef(
        clip_id="clip-hormuz-02",
        camera_id="cam-hormuz-01",
        recorded_at=_REF_NOW - timedelta(hours=2),
        duration_sec=180.0,
        url="/demo/clips/clip-hormuz-02.mp4",
        media_type="video/mp4",
        resolution_width=1920,
        resolution_height=1080,
        storage_key="demo/clips/clip-hormuz-02.mp4",
        is_loopable=True,
        provenance="demo-seed",
    )

    # ── Camera 2: Drone over Black Sea ────────────────────────────────────────
    georeg_blacksea = GeoRegistration(
        lon=32.150,
        lat=43.220,
        altitude_m=500.0,
        heading_deg=180.0,
        pitch_deg=-45.0,
        fov_horizontal_deg=70.0,
        fov_vertical_deg=55.0,
        is_mobile=True,
    )
    _camera_store["cam-blacksea-drone-01"] = georeg_blacksea
    _camera_meta["cam-blacksea-drone-01"] = {
        "camera_id": "cam-blacksea-drone-01",
        "camera_type": "optical",
        "label": "Black Sea Drone — mobile ISR",
        "geo_registration": georeg_blacksea,
    }

    obs2 = CameraObservation(
        camera_id="cam-blacksea-drone-01",
        observation_id="obs-blacksea-drone-01-001",
        observed_at=_REF_NOW - timedelta(hours=4),
        camera_type="optical",
        geo_registration=georeg_blacksea,
        clip_ref="/demo/clips/clip-blacksea-01.mp4",
        clip_start_offset_sec=0.0,
        clip_duration_sec=120.0,
        thumbnail_url="/demo/clips/clip-blacksea-01-thumb.jpg",
        confidence=0.91,
        source="argus-drone-blacksea",
        provenance="demo-seed",
        tags=["black-sea", "naval", "mobile", "isr"],
    )
    _observation_store[obs2.observation_id] = obs2

    _clip_store["clip-blacksea-01"] = MediaClipRef(
        clip_id="clip-blacksea-01",
        camera_id="cam-blacksea-drone-01",
        recorded_at=_REF_NOW - timedelta(hours=4),
        duration_sec=120.0,
        url="/demo/clips/clip-blacksea-01.mp4",
        media_type="video/mp4",
        resolution_width=1280,
        resolution_height=720,
        storage_key="demo/clips/clip-blacksea-01.mp4",
        is_loopable=True,
        provenance="demo-seed",
    )

    # ── Camera 3: Thermal radar at Baltic ────────────────────────────────────
    georeg_baltic = GeoRegistration(
        lon=20.500,
        lat=57.800,
        altitude_m=30.0,
        heading_deg=0.0,
        pitch_deg=-5.0,
        fov_horizontal_deg=120.0,
        fov_vertical_deg=40.0,
        is_mobile=False,
    )
    _camera_store["cam-baltic-thermal-01"] = georeg_baltic
    _camera_meta["cam-baltic-thermal-01"] = {
        "camera_id": "cam-baltic-thermal-01",
        "camera_type": "thermal",
        "label": "Baltic Thermal Radar — shore station",
        "geo_registration": georeg_baltic,
    }

    obs3 = CameraObservation(
        camera_id="cam-baltic-thermal-01",
        observation_id="obs-baltic-thermal-01-001",
        observed_at=_REF_NOW - timedelta(hours=1),
        camera_type="thermal",
        geo_registration=georeg_baltic,
        clip_ref="/demo/clips/clip-baltic-thermal-01.mp4",
        clip_start_offset_sec=0.0,
        clip_duration_sec=600.0,
        thumbnail_url="/demo/clips/clip-baltic-thermal-01-thumb.jpg",
        confidence=0.85,
        source="argus-thermal-baltic",
        provenance="demo-seed",
        tags=["baltic", "thermal", "maritime-border"],
    )
    _observation_store[obs3.observation_id] = obs3

    _clip_store["clip-baltic-thermal-01"] = MediaClipRef(
        clip_id="clip-baltic-thermal-01",
        camera_id="cam-baltic-thermal-01",
        recorded_at=_REF_NOW - timedelta(hours=1),
        duration_sec=600.0,
        url="/demo/clips/clip-baltic-thermal-01.mp4",
        media_type="video/mp4",
        resolution_width=640,
        resolution_height=480,
        storage_key="demo/clips/clip-baltic-thermal-01.mp4",
        is_loopable=True,
        provenance="demo-seed",
    )
    _clip_store["clip-baltic-thermal-02"] = MediaClipRef(
        clip_id="clip-baltic-thermal-02",
        camera_id="cam-baltic-thermal-01",
        recorded_at=_REF_NOW - timedelta(minutes=30),
        duration_sec=300.0,
        url="/demo/clips/clip-baltic-thermal-02.mp4",
        media_type="video/mp4",
        resolution_width=640,
        resolution_height=480,
        storage_key="demo/clips/clip-baltic-thermal-02.mp4",
        is_loopable=True,
        provenance="demo-seed",
    )

    # ── Seed detections tied to observations ─────────────────────────────────
    # Vessel detection at Hormuz
    _detection_store["det-001"] = DetectionOverlay(
        detection_id="det-001",
        observation_id="obs-hormuz-01-001",
        detected_at=_REF_NOW - timedelta(hours=6),
        detection_type="vessel",
        bounding_box={"x": 0.35, "y": 0.50, "width": 0.20, "height": 0.15},
        geo_location={"lon": 56.42, "lat": 26.60, "altitude_m": 0.0},
        confidence=0.93,
        model_version="argus-det-v1.2",
        evidence_refs=[],
        source="argus-cctv-hormuz",
        provenance="demo-seed",
    )
    # Vehicle detection at Hormuz
    _detection_store["det-002"] = DetectionOverlay(
        detection_id="det-002",
        observation_id="obs-hormuz-01-001",
        detected_at=_REF_NOW - timedelta(hours=5, minutes=45),
        detection_type="vehicle",
        bounding_box={"x": 0.60, "y": 0.70, "width": 0.08, "height": 0.06},
        geo_location={"lon": 56.41, "lat": 26.59, "altitude_m": 0.0},
        confidence=0.78,
        model_version="argus-det-v1.2",
        evidence_refs=[],
        source="argus-cctv-hormuz",
        provenance="demo-seed",
    )
    # Aircraft detection Black Sea drone
    _detection_store["det-003"] = DetectionOverlay(
        detection_id="det-003",
        observation_id="obs-blacksea-drone-01-001",
        detected_at=_REF_NOW - timedelta(hours=4),
        detection_type="aircraft",
        bounding_box={"x": 0.25, "y": 0.20, "width": 0.05, "height": 0.03},
        geo_location={"lon": 32.13, "lat": 43.23, "altitude_m": 1200.0},
        confidence=0.66,
        model_version="argus-det-v1.2",
        evidence_refs=[],
        source="argus-drone-blacksea",
        provenance="demo-seed",
    )
    # Vehicle detection Black Sea drone
    _detection_store["det-004"] = DetectionOverlay(
        detection_id="det-004",
        observation_id="obs-blacksea-drone-01-001",
        detected_at=_REF_NOW - timedelta(hours=3, minutes=50),
        detection_type="vehicle",
        bounding_box={"x": 0.48, "y": 0.65, "width": 0.07, "height": 0.05},
        geo_location={"lon": 32.16, "lat": 43.21, "altitude_m": 0.0},
        confidence=0.82,
        model_version="argus-det-v1.2",
        evidence_refs=[],
        source="argus-drone-blacksea",
        provenance="demo-seed",
    )
    # Infrastructure detection Baltic thermal
    _detection_store["det-005"] = DetectionOverlay(
        detection_id="det-005",
        observation_id="obs-baltic-thermal-01-001",
        detected_at=_REF_NOW - timedelta(hours=1),
        detection_type="infrastructure",
        bounding_box={"x": 0.10, "y": 0.30, "width": 0.40, "height": 0.25},
        geo_location={"lon": 20.50, "lat": 57.81, "altitude_m": 0.0},
        confidence=0.95,
        model_version="argus-det-v1.2",
        evidence_refs=[],
        source="argus-thermal-baltic",
        provenance="demo-seed",
    )


_seed()


# ── Endpoints — static routes FIRST to avoid param capture ───────────────────


@router.get(
    "",
    response_model=List[Dict],
    summary="List all cameras",
    description="Returns camera IDs, type, label, and geo_registration for all seeded cameras.",
)
def list_cameras() -> List[Dict]:
    return list(_camera_meta.values())


@router.get(
    "/detections",
    response_model=List[DetectionOverlay],
    summary="List detection overlays for all cameras",
    description=(
        "Returns detection overlay events across all cameras.  "
        "Optionally filter by detection_type and/or confidence_min."
    ),
)
def list_detections(
    detection_type: Optional[str] = Query(
        default=None,
        description="Filter by type: vehicle | person | aircraft | vessel | infrastructure | unknown",
    ),
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
) -> List[DetectionOverlay]:
    results = list(_detection_store.values())
    if detection_type is not None:
        results = [d for d in results if d.detection_type == detection_type]
    if confidence_min > 0.0:
        results = [d for d in results if d.confidence >= confidence_min]
    results.sort(key=lambda d: d.detected_at, reverse=True)
    return results


@router.get(
    "/{camera_id}",
    response_model=Dict,
    summary="Get a single camera by ID",
    description="Returns the camera metadata and geo_registration for the given camera_id.",
)
def get_camera(camera_id: str) -> Dict:
    meta = _camera_meta.get(camera_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id!r} not found")
    return meta


@router.get(
    "/{camera_id}/observations",
    response_model=List[CameraObservation],
    summary="List observations for a camera",
    description=(
        "Returns observations for the given camera.  "
        "Optional start/end filters accept ISO 8601 UTC datetimes."
    ),
)
def list_observations(
    camera_id: str,
    start: Optional[datetime] = Query(
        default=None, description="Filter observations on or after this UTC timestamp"
    ),
    end: Optional[datetime] = Query(
        default=None, description="Filter observations on or before this UTC timestamp"
    ),
    limit: int = Query(default=50, ge=1, le=500, description="Maximum results to return"),
) -> List[CameraObservation]:
    if camera_id not in _camera_store:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id!r} not found")
    results = [o for o in _observation_store.values() if o.camera_id == camera_id]
    if start is not None:
        results = [o for o in results if o.observed_at >= start]
    if end is not None:
        results = [o for o in results if o.observed_at <= end]
    results.sort(key=lambda o: o.observed_at, reverse=True)
    return results[:limit]


@router.get(
    "/{camera_id}/clips",
    response_model=List[MediaClipRef],
    summary="List clips for a camera",
    description="Returns media clip references for the given camera, optionally filtered by time range.",
)
def list_clips(
    camera_id: str,
    start: Optional[datetime] = Query(
        default=None, description="Filter clips recorded on or after this UTC timestamp"
    ),
    end: Optional[datetime] = Query(
        default=None, description="Filter clips recorded on or before this UTC timestamp"
    ),
) -> List[MediaClipRef]:
    if camera_id not in _camera_store:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id!r} not found")
    results = [c for c in _clip_store.values() if c.camera_id == camera_id]
    if start is not None:
        results = [c for c in results if c.recorded_at >= start]
    if end is not None:
        results = [c for c in results if c.recorded_at <= end]
    results.sort(key=lambda c: c.recorded_at, reverse=True)
    return results


@router.post(
    "/{camera_id}/observations",
    response_model=CameraObservation,
    status_code=201,
    summary="Register a new camera observation",
    description=(
        "Appends a new CameraObservation to the in-memory store. "
        "The camera_id in the URL must match the body's camera_id."
    ),
)
def create_observation(camera_id: str, obs: CameraObservation) -> CameraObservation:
    if camera_id not in _camera_store:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id!r} not found")
    if obs.camera_id != camera_id:
        raise HTTPException(
            status_code=422,
            detail=f"camera_id mismatch: URL={camera_id!r}, body={obs.camera_id!r}",
        )
    if obs.observation_id in _observation_store:
        raise HTTPException(
            status_code=409,
            detail=f"Observation {obs.observation_id!r} already exists",
        )
    _observation_store[obs.observation_id] = obs
    return obs
