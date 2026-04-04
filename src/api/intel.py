"""Intelligence briefing REST API — P6-6.

GET /api/v1/intel/briefing — returns current intelligence assessment
"""
from __future__ import annotations

from fastapi import APIRouter

from src.services.intel_briefing import IntelBriefing, generate_briefing

router = APIRouter(prefix="/api/v1/intel", tags=["intel"])


@router.get("/briefing", response_model=IntelBriefing, summary="Current intelligence briefing")
def get_briefing() -> IntelBriefing:
    return generate_briefing()
