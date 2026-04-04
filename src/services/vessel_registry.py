from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class VesselType(str, Enum):
    VLCC = "VLCC"
    SUEZMAX = "Suezmax"
    AFRAMAX = "Aframax"
    PATROL = "Patrol Craft"
    SUPPLY = "Supply Vessel"
    CONTAINER = "Container"
    TANKER = "Product Tanker"
    BULK = "Bulk Carrier"


class SanctionsStatus(str, Enum):
    CLEAN = "clean"
    OFAC_SDN = "OFAC-SDN"
    UN_SANCTIONED = "UN-sanctioned"
    EU_SANCTIONED = "EU-sanctioned"
    SHADOW_FLEET = "shadow-fleet"
    WATCH_LIST = "watch-list"


class VesselProfile(BaseModel):
    imo: str
    mmsi: str
    name: str
    flag: str
    flag_emoji: str
    vessel_type: VesselType
    gross_tonnage: int
    year_built: int
    owner: str
    operator: str
    sanctions_status: SanctionsStatus
    sanctions_detail: str = ""
    dark_ship_risk: str
    last_known_port: str
    notes: str = ""


_VESSELS: List[Dict[str, Any]] = [
    # Sanctioned / IRGC-affiliated tankers
    {"imo":"9169501","mmsi":"422110600","name":"WISDOM","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"VLCC",
     "gross_tonnage":299999,"year_built":2000,"owner":"NITC","operator":"NITC",
     "sanctions_status":"OFAC-SDN","sanctions_detail":"OFAC designation 2019. Transports Iranian crude in violation of US sanctions.",
     "dark_ship_risk":"critical","last_known_port":"Kharg Island","notes":"Frequently goes dark near Hormuz."},
    {"imo":"9196330","mmsi":"422110700","name":"GRACE 1 (ADRIAN DARYA)","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"VLCC",
     "gross_tonnage":299994,"year_built":2000,"owner":"NITC","operator":"NITC",
     "sanctions_status":"OFAC-SDN","sanctions_detail":"Seized by UK Royal Marines 2019; renamed Adrian Darya 1 after release.",
     "dark_ship_risk":"critical","last_known_port":"Bandar Abbas"},
    {"imo":"9154671","mmsi":"422110800","name":"HORSE","flag":"CN","flag_emoji":"🇨🇳","vessel_type":"VLCC",
     "gross_tonnage":300000,"year_built":1996,"owner":"Marshall Islands shell company","operator":"Moonlight Shipping",
     "sanctions_status":"shadow-fleet","sanctions_detail":"OFAC Oct 2023 advisory: Iranian shadow fleet. Flag-of-convenience.",
     "dark_ship_risk":"critical","last_known_port":"Ningbo"},
    {"imo":"9215021","mmsi":"422011200","name":"SAVIZ","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Supply Vessel",
     "gross_tonnage":11500,"year_built":2000,"owner":"IRGC Quds Force (alleged)","operator":"IRISL",
     "sanctions_status":"OFAC-SDN","sanctions_detail":"Used as IRGC intelligence platform. Attacked in Red Sea 2021.",
     "dark_ship_risk":"high","last_known_port":"Djibouti"},
    {"imo":"9082547","mmsi":"422040600","name":"IRAN MAHAN","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Aframax",
     "gross_tonnage":80000,"year_built":1995,"owner":"NITC","operator":"NITC",
     "sanctions_status":"OFAC-SDN","dark_ship_risk":"high","last_known_port":"Bandar Abbas"},
    {"imo":"9078759","mmsi":"422040700","name":"DARYABAR","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Suezmax",
     "gross_tonnage":149997,"year_built":1994,"owner":"NITC","operator":"NITC",
     "sanctions_status":"OFAC-SDN","dark_ship_risk":"high","last_known_port":"Kharg Island"},
    {"imo":"9219208","mmsi":"422110900","name":"SEA ROSE","flag":"CV","flag_emoji":"🇨🇻","vessel_type":"VLCC",
     "gross_tonnage":300000,"year_built":2000,"owner":"Panama shell company","operator":"Unknown",
     "sanctions_status":"shadow-fleet","sanctions_detail":"Loaded at Kharg Island multiple times per AIS reconstruction.",
     "dark_ship_risk":"critical","last_known_port":"Ningbo"},
    {"imo":"9195268","mmsi":"422111000","name":"GULF SKY","flag":"PG","flag_emoji":"🇵🇬","vessel_type":"Suezmax",
     "gross_tonnage":150000,"year_built":1999,"owner":"Unknown","operator":"Unknown",
     "sanctions_status":"watch-list","dark_ship_risk":"high","last_known_port":"Khor Fakkan"},
    {"imo":"9160884","mmsi":"422111100","name":"IRAN NOOR","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Aframax",
     "gross_tonnage":84000,"year_built":1997,"owner":"NITC","operator":"NITC",
     "sanctions_status":"OFAC-SDN","dark_ship_risk":"high","last_known_port":"Bandar Abbas"},
    {"imo":"9219210","mmsi":"422111200","name":"HAPPINESS I","flag":"MN","flag_emoji":"🇲🇳","vessel_type":"VLCC",
     "gross_tonnage":299998,"year_built":2000,"owner":"Mongolia front company","operator":"Unknown",
     "sanctions_status":"shadow-fleet","dark_ship_risk":"critical","last_known_port":"Zhoushan"},
    # IRGC patrol craft
    {"imo":"N/A","mmsi":"422500001","name":"IRGCN PATROL-01","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Patrol Craft",
     "gross_tonnage":450,"year_built":2010,"owner":"IRGC Navy","operator":"IRGC Navy",
     "sanctions_status":"OFAC-SDN","sanctions_detail":"IRGC fast-attack craft operating within Hormuz TSS.",
     "dark_ship_risk":"low","last_known_port":"Bandar Abbas"},
    {"imo":"N/A","mmsi":"422500002","name":"IRGCN PATROL-02","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Patrol Craft",
     "gross_tonnage":450,"year_built":2012,"owner":"IRGC Navy","operator":"IRGC Navy",
     "sanctions_status":"OFAC-SDN","dark_ship_risk":"low","last_known_port":"Qeshm Island"},
    {"imo":"N/A","mmsi":"422500003","name":"IRGCN SHAHID BAGHERI","flag":"IR","flag_emoji":"🇮🇷","vessel_type":"Patrol Craft",
     "gross_tonnage":600,"year_built":2015,"owner":"IRGC Navy","operator":"IRGC Navy",
     "sanctions_status":"OFAC-SDN","dark_ship_risk":"medium","last_known_port":"Bandar Abbas"},
    # International reference vessels (clean)
    {"imo":"9384895","mmsi":"211330000","name":"EVER GRACE","flag":"LR","flag_emoji":"🇱🇷","vessel_type":"Container",
     "gross_tonnage":141000,"year_built":2009,"owner":"Evergreen Marine","operator":"Evergreen",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Singapore"},
    {"imo":"9432009","mmsi":"636017432","name":"STELLA MARINER","flag":"LR","flag_emoji":"🇱🇷","vessel_type":"Product Tanker",
     "gross_tonnage":82000,"year_built":2010,"owner":"Stena Line AB","operator":"Stena Tankers",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Rotterdam",
     "notes":"Sister vessel to Stena Impero seized by IRGC 2019."},
    {"imo":"9417418","mmsi":"352456000","name":"HORMUZ CARRIER","flag":"PA","flag_emoji":"🇵🇦","vessel_type":"Product Tanker",
     "gross_tonnage":62000,"year_built":2010,"owner":"Pacific Basin Shipping","operator":"Pacific Basin",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Abu Dhabi"},
    {"imo":"9453910","mmsi":"477123400","name":"PACIFIC VOYAGER","flag":"HK","flag_emoji":"🇭🇰","vessel_type":"VLCC",
     "gross_tonnage":305000,"year_built":2011,"owner":"Pacific International Lines","operator":"PIL",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Fujairah"},
    {"imo":"9481720","mmsi":"538006712","name":"ORIENT PEARL","flag":"MH","flag_emoji":"🇲🇭","vessel_type":"Suezmax",
     "gross_tonnage":160000,"year_built":2012,"owner":"International Seaways","operator":"INSW",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Muscat"},
    {"imo":"9234991","mmsi":"440123456","name":"EASTERN STAR","flag":"KR","flag_emoji":"🇰🇷","vessel_type":"Product Tanker",
     "gross_tonnage":55000,"year_built":2002,"owner":"SK Shipping","operator":"SK Shipping",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Sharjah"},
    {"imo":"9356789","mmsi":"249987000","name":"CASPIAN PRIDE","flag":"MT","flag_emoji":"🇲🇹","vessel_type":"Product Tanker",
     "gross_tonnage":50000,"year_built":2006,"owner":"TMS Tankers","operator":"TMS",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Khor Fakkan"},
    {"imo":"9312456","mmsi":"215631000","name":"GULF BREEZE","flag":"MT","flag_emoji":"🇲🇹","vessel_type":"Product Tanker",
     "gross_tonnage":46000,"year_built":2004,"owner":"Mediterranean Shipping","operator":"MSC",
     "sanctions_status":"clean","dark_ship_risk":"low","last_known_port":"Dubai"},
]

_INDEX: Dict[str, Dict[str, Any]] = {v["mmsi"]: v for v in _VESSELS}
_IMO_INDEX: Dict[str, Dict[str, Any]] = {v["imo"]: v for v in _VESSELS if v["imo"] != "N/A"}


def get_vessel_by_mmsi(mmsi: str) -> Optional[VesselProfile]:
    raw = _INDEX.get(mmsi)
    return VesselProfile(**raw) if raw else None


def get_vessel_by_imo(imo: str) -> Optional[VesselProfile]:
    raw = _IMO_INDEX.get(imo)
    return VesselProfile(**raw) if raw else None


def list_vessels(
    sanctions_only: bool = False,
    dark_risk: Optional[str] = None,
    vessel_type: Optional[str] = None,
    limit: int = 100,
) -> List[VesselProfile]:
    results = list(_VESSELS)
    if sanctions_only:
        results = [v for v in results if v["sanctions_status"] != "clean"]
    if dark_risk:
        results = [v for v in results if v["dark_ship_risk"] == dark_risk]
    if vessel_type:
        results = [v for v in results if v["vessel_type"].lower() == vessel_type.lower()]
    return [VesselProfile(**v) for v in results[:limit]]
