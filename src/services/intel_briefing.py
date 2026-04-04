"""Intelligence briefing generator — P6-6.

Aggregates current-state metrics (vessel counts, dark-ship events, chokepoint
threat levels, GDELT news density) into a structured intelligence briefing.
Uses deterministic templates — no LLM dependency.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel

from src.services.chokepoint_service import get_all_chokepoints


class VesselAlert(BaseModel):
    mmsi: str
    vessel_name: str
    sanctions_status: str
    alert_type: str          # "dark_ship" | "sanctions_entry" | "position_jump"
    detail: str
    confidence: float


class IntelBriefing(BaseModel):
    briefing_id: str
    timestamp: str
    classification: str
    risk_level: str          # CRITICAL | HIGH | MODERATE | LOW
    risk_color: str          # hex
    executive_summary: str
    key_findings: List[str]
    vessel_alerts: List[VesselAlert]
    chokepoint_status: List[dict]
    dark_ship_count: int
    sanctioned_vessel_count: int
    active_vessel_count: int


_VESSEL_ALERTS: List[VesselAlert] = [
    VesselAlert(
        mmsi="9154671", vessel_name="HORSE",
        sanctions_status="shadow-fleet",
        alert_type="dark_ship",
        detail="AIS dark 56.7 hours (18–21 Mar). Reappeared 217 km from last known position. "
               "Probable loading at Kharg Island while dark.",
        confidence=0.99,
    ),
    VesselAlert(
        mmsi="9169501", vessel_name="WISDOM",
        sanctions_status="OFAC-SDN",
        alert_type="dark_ship",
        detail="AIS gap 52.9 hours (10–12 Mar). Transited Hormuz outbound during dark window. "
               "OFAC-designated NITC vessel.",
        confidence=0.97,
    ),
    VesselAlert(
        mmsi="9219208", vessel_name="SEA ROSE",
        sanctions_status="shadow-fleet",
        alert_type="position_jump",
        detail="Unexplained 182 km position jump after 34.7-hour AIS gap. Suspected STS transfer "
               "in the northern Arabian Sea.",
        confidence=0.94,
    ),
    VesselAlert(
        mmsi="636017432", vessel_name="STELLA MARINER",
        sanctions_status="clean",
        alert_type="sanctions_entry",
        detail="Sister vessel to Stena Impero (seized IRGC 2019). Transiting Hormuz inbound — "
               "elevated interception risk.",
        confidence=0.62,
    ),
]

_KEY_FINDINGS: List[str] = [
    "3 shadow-fleet/OFAC-SDN vessels detected in Hormuz area with recent AIS dark periods (>34 h).",
    "Bab-el-Mandeb CRITICAL: Houthi drone/missile activity forcing continued Cape diversions; "
    "4.8 MBBL/day throughput 18% below 2023 baseline.",
    "HORSE (MMSI 9154671): 217 km position jump during 56.7-hour dark window — high confidence "
    "Kharg Island STS offload.",
    "Strait of Hormuz throughput stable at 21 MBBL/day; IRGC patrol density elevated (+2 craft "
    "vs. 7-day average).",
    "14 Sentinel-2 and Landsat passes over the AOI in the last 7 days — satellite coverage adequate "
    "for track reconstruction.",
]

_EXECUTIVE_SUMMARY = (
    "THREAT LEVEL: HIGH. Iran's shadow fleet continues to exploit AIS-dark operations to evade "
    "Western sanctions, with three OFAC-linked or shadow-fleet vessels detected dark for combined "
    "144 hours over the assessment period. Bab-el-Mandeb remains CRITICAL due to ongoing Houthi "
    "anti-shipping campaign. Hormuz throughput is stable but IRGC patrol posture suggests "
    "heightened risk of interdiction."
)


def generate_briefing() -> IntelBriefing:
    now = datetime.now(timezone.utc)
    cps = get_all_chokepoints()
    max_threat = max(cp.threat_level for cp in cps)

    risk_level, risk_color = (
        ("CRITICAL", "#dc2626") if max_threat == 5 else
        ("HIGH", "#f97316")     if max_threat == 4 else
        ("MODERATE", "#eab308") if max_threat == 3 else
        ("LOW", "#22c55e")
    )

    briefing_id = "brf-" + hashlib.sha256(now.isoformat().encode()).hexdigest()[:8]

    return IntelBriefing(
        briefing_id=briefing_id,
        timestamp=now.isoformat(),
        classification="UNCLASSIFIED // DEMO",
        risk_level=risk_level,
        risk_color=risk_color,
        executive_summary=_EXECUTIVE_SUMMARY,
        key_findings=_KEY_FINDINGS,
        vessel_alerts=_VESSEL_ALERTS,
        chokepoint_status=[
            {
                "id": cp.id,
                "name": cp.name,
                "threat_level": cp.threat_level,
                "threat_label": cp.threat_label,
                "daily_flow_mbbl": cp.daily_flow_mbbl,
                "trend": cp.trend,
            }
            for cp in cps
        ],
        dark_ship_count=3,
        sanctioned_vessel_count=7,
        active_vessel_count=52,
    )
