"""Chokepoint REST API — P6-1.

GET /api/v1/chokepoints              — list all chokepoints with current threat levels
GET /api/v1/chokepoints/{id}         — single chokepoint detail
GET /api/v1/chokepoints/{id}/metrics — 30-day flow / vessel / threat time series
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.services.chokepoint_service import (
    ChokepointListResponse,
    ChokepointMetricsResponse,
    get_all_chokepoints,
    get_chokepoint,
    get_chokepoint_metrics,
)

router = APIRouter(prefix="/api/v1/chokepoints", tags=["chokepoints"])


@router.get("", response_model=ChokepointListResponse, summary="List all chokepoints")
def list_chokepoints() -> ChokepointListResponse:
    return ChokepointListResponse(chokepoints=get_all_chokepoints())


@router.get("/{chokepoint_id}", summary="Get single chokepoint")
def get_one_chokepoint(chokepoint_id: str):
    cp = get_chokepoint(chokepoint_id)
    if not cp:
        raise HTTPException(status_code=404, detail=f"Chokepoint '{chokepoint_id}' not found")
    return cp


@router.get(
    "/{chokepoint_id}/metrics",
    response_model=ChokepointMetricsResponse,
    summary="30-day flow and threat metrics for a chokepoint",
)
def get_metrics(chokepoint_id: str) -> ChokepointMetricsResponse:
    metrics = get_chokepoint_metrics(chokepoint_id)
    if not metrics:
        raise HTTPException(status_code=404, detail=f"Chokepoint '{chokepoint_id}' not found")
    return metrics
