from __future__ import annotations
import hashlib, random
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

_TODAY = date(2026, 4, 4)


class ChokepointMetric(BaseModel):
    date: str
    daily_flow_mbbl: float
    vessel_count: int
    threat_level: int


class Chokepoint(BaseModel):
    id: str
    name: str
    controlling_nation: str
    geometry: Dict[str, Any]
    centroid: Dict[str, float]
    daily_flow_mbbl: float
    vessel_count_24h: int
    threat_level: int
    threat_label: str
    trend: str
    description: str


class ChokepointListResponse(BaseModel):
    chokepoints: List[Chokepoint]


class ChokepointMetricsResponse(BaseModel):
    chokepoint_id: str
    name: str
    metrics: List[ChokepointMetric]


_CHOKEPOINTS: List[Dict[str, Any]] = [
    {
        "id": "hormuz", "name": "Strait of Hormuz",
        "controlling_nation": "Iran / Oman",
        "centroid": {"lon": 56.52, "lat": 26.35},
        "geometry": {"type": "Polygon", "coordinates": [[[56.15, 26.00], [56.60, 25.85], [57.05, 25.90],
            [57.30, 26.20], [57.10, 26.75], [56.55, 26.85], [56.10, 26.72], [55.95, 26.40], [56.15, 26.00]]]},
        "daily_flow_mbbl": 21.0, "vessel_count_24h": 52, "threat_level": 4,
        "threat_label": "HIGH", "trend": "-",
        "description": "~21 million barrels/day — ~20% of global petroleum trade. Iran controls the northern "
                       "shoreline and has repeatedly threatened closure. IRGC fast-attack patrol craft conduct "
                       "daily operations within the strait.",
    },
    {
        "id": "bab-el-mandeb", "name": "Bab-el-Mandeb",
        "controlling_nation": "Djibouti / Yemen / Eritrea",
        "centroid": {"lon": 43.38, "lat": 12.45},
        "geometry": {"type": "Polygon", "coordinates": [[[42.95, 11.90], [43.40, 11.85], [43.80, 12.05],
            [43.90, 12.60], [43.55, 13.00], [43.10, 13.05], [42.85, 12.70], [42.90, 12.20], [42.95, 11.90]]]},
        "daily_flow_mbbl": 4.8, "vessel_count_24h": 28, "threat_level": 5,
        "threat_label": "CRITICAL", "trend": "-",
        "description": "Houthi forces have attacked commercial shipping since Nov 2023, forcing many carriers onto "
                       "the South Africa Cape route. Major disruption to global container trade and energy flows.",
    },
    {
        "id": "suez", "name": "Suez Canal",
        "controlling_nation": "Egypt",
        "centroid": {"lon": 32.55, "lat": 30.20},
        "geometry": {"type": "Polygon", "coordinates": [[[32.30, 29.90], [32.55, 29.85], [32.80, 29.90],
            [32.85, 30.55], [32.70, 30.60], [32.45, 30.55], [32.35, 30.25], [32.30, 29.90]]]},
        "daily_flow_mbbl": 2.2, "vessel_count_24h": 48, "threat_level": 2,
        "threat_label": "ELEVATED", "trend": "+",
        "description": "Connects Mediterranean and Red Sea, cutting 7,000 nm off the Europe-Asia route. "
                       "10% of global trade by value transits annually.",
    },
    {
        "id": "malacca", "name": "Strait of Malacca",
        "controlling_nation": "Malaysia / Singapore / Indonesia",
        "centroid": {"lon": 103.50, "lat": 2.50},
        "geometry": {"type": "Polygon", "coordinates": [[[100.50, 1.20], [102.00, 0.80], [104.00, 1.10],
            [104.50, 2.30], [104.20, 3.80], [103.00, 4.20], [101.50, 3.50], [100.50, 2.50], [100.50, 1.20]]]},
        "daily_flow_mbbl": 16.0, "vessel_count_24h": 180, "threat_level": 2,
        "threat_label": "ELEVATED", "trend": "=",
        "description": "Handles ~30% of global trade including bulk of Middle East energy shipments to East Asia. "
                       "Depth constraints (25m draft) limit VLCC throughput.",
    },
]


def _rng_for(cid: str, day_offset: int) -> random.Random:
    seed = int(hashlib.sha256(f"{cid}:{day_offset}".encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def _get_metrics_30d(cid: str, base_flow: float, base_vessels: int, base_threat: int) -> List[ChokepointMetric]:
    metrics: List[ChokepointMetric] = []
    for offset in range(29, -1, -1):
        d = _TODAY - timedelta(days=offset)
        rng = _rng_for(cid, offset)
        flow = round(base_flow + rng.gauss(0, base_flow * 0.03), 2)
        vessels = max(0, base_vessels + rng.randint(-5, 5))
        threat = max(1, min(5, base_threat + rng.choice([-1, 0, 0, 0, 1])))
        metrics.append(ChokepointMetric(date=d.isoformat(), daily_flow_mbbl=flow, vessel_count=vessels, threat_level=threat))
    return metrics


def get_all_chokepoints() -> List[Chokepoint]:
    return [Chokepoint(**cp) for cp in _CHOKEPOINTS]


def get_chokepoint(cid: str) -> Optional[Chokepoint]:
    for cp in _CHOKEPOINTS:
        if cp["id"] == cid:
            return Chokepoint(**cp)
    return None


def get_chokepoint_metrics(cid: str) -> Optional[ChokepointMetricsResponse]:
    cp = next((c for c in _CHOKEPOINTS if c["id"] == cid), None)
    if not cp:
        return None
    metrics = _get_metrics_30d(cid, cp["daily_flow_mbbl"], cp["vessel_count_24h"], cp["threat_level"])
    return ChokepointMetricsResponse(chokepoint_id=cid, name=cp["name"], metrics=metrics)
