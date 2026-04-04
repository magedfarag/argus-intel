"""Detection overlay router — Phase 4, Track B / Track D.

GET  /api/v1/detections                           — list all detections
     query: detection_type, confidence_min, observation_id
GET  /api/v1/detections/{detection_id}            — single detection detail
POST /api/v1/detections/{detection_id}/evidence   — link EvidenceLink to a detection

The _detection_store is shared with src.api.cameras; detections are seeded
there.  This router imports that store directly so both endpoints reflect the
same data without duplication.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.cameras import _detection_store
from src.models.operational_layers import EvidenceLink
from src.models.sensor_fusion import DetectionOverlay

router = APIRouter(prefix="/api/v1/detections", tags=["detections"])

# Per-detection evidence lists (idempotent by evidence_id)
_detection_evidence: Dict[str, List[EvidenceLink]] = {
    det_id: [] for det_id in _detection_store
}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=List[DetectionOverlay],
    summary="List detection overlays",
    description=(
        "Returns detection overlay events across all cameras.  "
        "Optional filters: detection_type, confidence_min, observation_id."
    ),
)
def list_detections(
    detection_type: Optional[str] = Query(
        default=None,
        description="vehicle | person | aircraft | vessel | infrastructure | unknown",
    ),
    confidence_min: float = Query(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    observation_id: Optional[str] = Query(
        default=None, description="Filter by parent observation_id"
    ),
) -> List[DetectionOverlay]:
    results = list(_detection_store.values())
    if detection_type is not None:
        results = [d for d in results if d.detection_type == detection_type]
    if confidence_min > 0.0:
        results = [d for d in results if d.confidence >= confidence_min]
    if observation_id is not None:
        results = [d for d in results if d.observation_id == observation_id]
    results.sort(key=lambda d: d.detected_at, reverse=True)
    return results


@router.get(
    "/{detection_id}",
    response_model=DetectionOverlay,
    summary="Get a single detection by ID",
    description="Returns the full DetectionOverlay including any attached evidence_refs.",
)
def get_detection(detection_id: str) -> DetectionOverlay:
    det = _detection_store.get(detection_id)
    if det is None:
        raise HTTPException(
            status_code=404, detail=f"Detection {detection_id!r} not found"
        )
    return det


@router.post(
    "/{detection_id}/evidence",
    response_model=DetectionOverlay,
    summary="Attach an evidence link to a detection",
    description=(
        "Appends an EvidenceLink to the detection's evidence_refs list.  "
        "Idempotent: duplicate evidence_ids are silently ignored."
    ),
)
def attach_evidence(detection_id: str, link: EvidenceLink) -> DetectionOverlay:
    det = _detection_store.get(detection_id)
    if det is None:
        raise HTTPException(
            status_code=404, detail=f"Detection {detection_id!r} not found"
        )

    existing_ids = {el.evidence_id for el in _detection_evidence.get(detection_id, [])}
    if link.evidence_id not in existing_ids:
        _detection_evidence.setdefault(detection_id, []).append(link)
        updated_refs = list(det.evidence_refs) + [link.evidence_id]
        updated = det.model_copy(update={"evidence_refs": updated_refs})
        _detection_store[detection_id] = updated
        return updated

    return det
