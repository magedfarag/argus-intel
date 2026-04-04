"""Satellite orbit and pass stub connector — Track A, Phase 2.

Implements TLE-based orbit ingestion and deterministic pass prediction for
demo environments.  No HTTP calls are made; all outputs are synthetic and
reproducible.

connector_id: ``celestrak-tle-stub``
source_type:  ``telemetry``

Design notes:
- TLE triplets (name, line1, line2) are parsed with a minimal pure-Python
  parser; no sgp4 dependency required for the stub.
- Pass prediction uses a simplified flat-Earth ground-track model:
  passes are generated every ``orbital_period_minutes`` starting from an
  epoch anchored to the TLE epoch, offset by a deterministic phase derived
  from the satellite's NORAD ID.
- All outputs carry ``source="celestrak_tle_stub"`` provenance.
- ``to_canonical_event()`` helpers on ``SatelliteOrbit`` / ``SatellitePass``
  are exposed as free functions here so the store integration stays clean.
"""
from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.connectors.base import (
    BaseConnector,
    ConnectorHealthStatus,
    NormalizationError,
)
from src.models.canonical_event import (
    CanonicalEvent,
    CorrelationKeys,
    EntityType,
    EventType,
    LicenseRecord,
    NormalizationRecord,
    ProvenanceRecord,
    SourceType,
    make_event_id,
)
from src.models.operational_layers import SatelliteOrbit, SatellitePass

logger = logging.getLogger(__name__)

_SOURCE = "celestrak_tle_stub"

# TLE license: public domain / Celestrak unrestricted.
_LICENSE = LicenseRecord(
    access_tier="public",
    commercial_use="allowed",
    redistribution="allowed",
    attribution_required=True,
)

# ────────────────────────────────────────────────────────────────────────────
# TLE parse helpers
# ────────────────────────────────────────────────────────────────────────────

def _parse_tle_triplet(name: str, line1: str, line2: str) -> SatelliteOrbit:
    """Parse a TLE triplet into a ``SatelliteOrbit``.

    Extracts NORAD ID, inclination, and mean motion (→ orbital period).
    Field offsets follow the TLE standard (fixed-column format).
    """
    name = name.strip()
    line1 = line1.strip()
    line2 = line2.strip()

    try:
        norad_id = int(line1[2:7].strip())
    except (ValueError, IndexError):
        norad_id = None

    try:
        inclination_deg = float(line2[8:16].strip())
    except (ValueError, IndexError):
        inclination_deg = None

    # Mean motion in revolutions per day → orbital period in minutes
    try:
        mean_motion_rev_per_day = float(line2[52:63].strip())
        orbital_period_minutes = 1440.0 / mean_motion_rev_per_day if mean_motion_rev_per_day > 0 else None
    except (ValueError, IndexError):
        orbital_period_minutes = None

    # Rough altitude estimate from period via vis-viva
    altitude_km: Optional[float] = None
    if orbital_period_minutes is not None:
        try:
            # Kepler's third law: T^2 ∝ a^3  (Earth GM = 3.986e5 km³/s²)
            T_s = orbital_period_minutes * 60.0
            RE = 6371.0  # km
            GM = 3.986004418e5  # km³/s²
            a_km = (GM * (T_s / (2 * math.pi)) ** 2) ** (1.0 / 3.0)
            altitude_km = round(a_km - RE, 1)
        except Exception:
            pass

    return SatelliteOrbit(
        satellite_id=name.upper().replace(" ", "-"),
        norad_id=norad_id,
        tle_line1=line1,
        tle_line2=line2,
        orbital_period_minutes=orbital_period_minutes,
        inclination_deg=inclination_deg,
        altitude_km=altitude_km,
        source=_SOURCE,
        loaded_at=datetime.now(timezone.utc),
    )


# ────────────────────────────────────────────────────────────────────────────
# Canonical-event conversion helpers
# ────────────────────────────────────────────────────────────────────────────

def orbit_to_canonical_event(orbit: SatelliteOrbit) -> CanonicalEvent:
    """Convert a ``SatelliteOrbit`` to a ``CanonicalEvent`` for ingest."""
    # Use the sub-satellite point at the equator as a proxy centroid when no
    # true position is available.
    centroid: Dict[str, Any] = {"type": "Point", "coordinates": [0.0, 0.0]}
    geometry: Dict[str, Any] = {"type": "Point", "coordinates": [0.0, 0.0]}

    event_time_str = orbit.loaded_at.isoformat()
    event_id = make_event_id(_SOURCE, orbit.satellite_id, orbit.loaded_at)

    return CanonicalEvent(
        event_id=event_id,
        source=_SOURCE,
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.IMAGERY_SCENE,
        entity_id=orbit.satellite_id,
        event_type=EventType.SATELLITE_ORBIT,
        event_time=orbit.loaded_at,
        geometry=geometry,
        centroid=centroid,
        confidence=1.0,
        attributes={
            "satellite_id": orbit.satellite_id,
            "norad_id": orbit.norad_id,
            "orbital_period_minutes": orbit.orbital_period_minutes,
            "inclination_deg": orbit.inclination_deg,
            "altitude_km": orbit.altitude_km,
        },
        normalization=NormalizationRecord(
            normalized_by="connector.orbit.tle_stub",
        ),
        provenance=ProvenanceRecord(
            raw_source_ref=f"tle_stub://{orbit.satellite_id}",
            source_record_id=orbit.satellite_id,
        ),
        license=_LICENSE,
    )


def pass_to_canonical_event(sp: SatellitePass) -> CanonicalEvent:
    """Convert a ``SatellitePass`` to a ``CanonicalEvent`` for ingest."""
    if sp.footprint_geojson:
        geometry = sp.footprint_geojson
        # Compute centroid from polygon ring
        coords = geometry.get("coordinates", [[]])[0]
        if coords:
            avg_lon = sum(c[0] for c in coords) / len(coords)
            avg_lat = sum(c[1] for c in coords) / len(coords)
            centroid: Dict[str, Any] = {"type": "Point", "coordinates": [round(avg_lon, 4), round(avg_lat, 4)]}
        else:
            centroid = {"type": "Point", "coordinates": [0.0, 0.0]}
    else:
        geometry = {"type": "Point", "coordinates": [0.0, 0.0]}
        centroid = {"type": "Point", "coordinates": [0.0, 0.0]}

    event_id = make_event_id(_SOURCE, sp.satellite_id, sp.aos)

    return CanonicalEvent(
        event_id=event_id,
        source=_SOURCE,
        source_type=SourceType.TELEMETRY,
        entity_type=EntityType.IMAGERY_SCENE,
        entity_id=sp.satellite_id,
        event_type=EventType.SATELLITE_PASS,
        event_time=sp.aos,
        time_start=sp.aos,
        time_end=sp.los,
        geometry=geometry,
        centroid=centroid,
        confidence=sp.confidence,
        attributes={
            "satellite_id": sp.satellite_id,
            "norad_id": sp.norad_id,
            "aos": sp.aos.isoformat(),
            "los": sp.los.isoformat(),
            "max_elevation_deg": sp.max_elevation_deg,
            "sensor_type": sp.sensor_type,
        },
        normalization=NormalizationRecord(
            normalized_by="connector.orbit.tle_stub",
        ),
        provenance=ProvenanceRecord(
            raw_source_ref=f"tle_stub://{sp.satellite_id}/pass/{sp.aos.isoformat()}",
            source_record_id=f"{sp.satellite_id}_{sp.aos.isoformat()}",
        ),
        license=_LICENSE,
    )


# ────────────────────────────────────────────────────────────────────────────
# Footprint helper
# ────────────────────────────────────────────────────────────────────────────

def _make_footprint(lon: float, lat: float, half_width_deg: float = 1.0) -> Dict[str, Any]:
    """Return a simple square GeoJSON Polygon centred on (lon, lat)."""
    dlon = half_width_deg
    dlat = half_width_deg * 0.75
    ring = [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


# ────────────────────────────────────────────────────────────────────────────
# OrbitConnector
# ────────────────────────────────────────────────────────────────────────────

class OrbitConnector(BaseConnector):
    """Stub connector for satellite orbit and pass data.

    Supports TLE ingestion and deterministic pass prediction.
    No network calls are made — all outputs are synthetic.
    """

    connector_id: str = "celestrak-tle-stub"
    display_name: str = "CelesTrak TLE Stub"
    source_type: str = "telemetry"

    # In-memory TLE catalogue keyed by satellite_id.
    _orbits: Dict[str, SatelliteOrbit]

    def __init__(self) -> None:
        self._orbits: Dict[str, SatelliteOrbit] = {}
        self._connected: bool = False

    # ── BaseConnector abstract methods ────────────────────────────────────

    def connect(self) -> None:
        """No remote endpoint; mark as connected immediately."""
        self._connected = True
        logger.info("OrbitConnector: stub connected (no remote endpoint).")

    def fetch(
        self,
        geometry: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Return raw TLE dicts for all loaded orbits (geometry/time ignored for stub)."""
        return [
            {
                "satellite_id": orb.satellite_id,
                "norad_id": orb.norad_id,
                "tle_line1": orb.tle_line1,
                "tle_line2": orb.tle_line2,
                "source": orb.source,
                "loaded_at": orb.loaded_at.isoformat(),
            }
            for orb in self._orbits.values()
        ]

    def normalize(self, raw: Dict[str, Any]) -> CanonicalEvent:
        """Normalize a raw TLE dict into a CanonicalEvent.

        ``raw`` must contain at minimum ``satellite_id`` and ``loaded_at``.
        """
        try:
            satellite_id: str = raw["satellite_id"]
            loaded_at_raw = raw.get("loaded_at", datetime.now(timezone.utc).isoformat())
            if isinstance(loaded_at_raw, str):
                loaded_at = datetime.fromisoformat(loaded_at_raw.replace("Z", "+00:00"))
            else:
                loaded_at = loaded_at_raw

            orbit = SatelliteOrbit(
                satellite_id=satellite_id,
                norad_id=raw.get("norad_id"),
                tle_line1=raw.get("tle_line1"),
                tle_line2=raw.get("tle_line2"),
                orbital_period_minutes=raw.get("orbital_period_minutes"),
                inclination_deg=raw.get("inclination_deg"),
                altitude_km=raw.get("altitude_km"),
                source=raw.get("source", _SOURCE),
                loaded_at=loaded_at,
            )
        except Exception as exc:
            raise NormalizationError(f"Cannot normalize TLE record: {exc}") from exc

        return orbit_to_canonical_event(orbit)

    def health(self) -> ConnectorHealthStatus:
        """Return health snapshot — always healthy for stub."""
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            healthy=True,
            message="Stub connector — always healthy",
            last_successful_poll=datetime.now(timezone.utc),
            error_count=0,
        )

    # ── Orbit-specific public API ─────────────────────────────────────────

    def ingest_orbits(self, tle_data: str) -> List[SatelliteOrbit]:
        """Parse newline-separated TLE triplets and return ``SatelliteOrbit`` list.

        Expected format (each triplet is three consecutive non-blank lines)::

            ISS (ZARYA)
            1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994
            2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000 39123

        Lines that are blank or start with '#' are ignored.  Any partial
        triplet at the end of the input is silently discarded.
        """
        lines = [ln for ln in tle_data.splitlines() if ln.strip() and not ln.startswith("#")]
        orbits: List[SatelliteOrbit] = []
        i = 0
        while i + 2 < len(lines):
            name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
            # Validate TLE line identifiers
            if line1.startswith("1 ") and line2.startswith("2 "):
                try:
                    orbit = _parse_tle_triplet(name, line1, line2)
                    self._orbits[orbit.satellite_id] = orbit
                    orbits.append(orbit)
                    logger.debug("OrbitConnector: loaded orbit for %s", orbit.satellite_id)
                except Exception as exc:
                    logger.warning("OrbitConnector: skipping malformed TLE triplet '%s': %s", name, exc)
                i += 3
            else:
                # Skip unexpected lines
                i += 1
        return orbits

    def compute_passes(
        self,
        satellite_id: str,
        lon: float,
        lat: float,
        horizon_hours: int = 24,
    ) -> List[SatellitePass]:
        """Compute deterministic synthetic passes for a satellite above a location.

        The algorithm uses the satellite's orbital period to schedule passes at
        regular intervals.  A deterministic phase offset (derived from the
        satellite's NORAD ID or a hash of its name) ensures that different
        satellites have different but reproducible pass times.

        For a proper pass computation, replace this stub with an sgp4-based
        implementation and real observer geometry.

        Args:
            satellite_id: Canonical satellite identifier (matches ``SatelliteOrbit.satellite_id``).
            lon:          Observer longitude (decimal degrees, WGS-84).
            lat:          Observer latitude (decimal degrees, WGS-84).
            horizon_hours: Number of hours ahead to compute passes.

        Returns:
            List of ``SatellitePass`` objects, sorted by AOS ascending.

        Raises:
            KeyError: If ``satellite_id`` is not loaded in the internal orbit store.
        """
        orbit = self._orbits.get(satellite_id)
        if orbit is None:
            raise KeyError(f"Satellite not loaded: {satellite_id!r}")

        period_min = orbit.orbital_period_minutes or 90.0  # fallback to 90 min

        # Deterministic phase offset to avoid all sats having identical windows
        phase_seed = orbit.norad_id if orbit.norad_id else int(
            hashlib.sha256(satellite_id.encode()).hexdigest(), 16
        )
        phase_offset_min = (phase_seed % int(period_min)) * 1.0

        now_utc = datetime.now(timezone.utc)
        window_end = now_utc + timedelta(hours=horizon_hours)

        passes: List[SatellitePass] = []
        # First AOS is at now + phase_offset, then every period_min
        t = now_utc + timedelta(minutes=phase_offset_min % period_min)

        # Sensor swath width: ±1° lon, ±0.5° lat (very rough 2-km equivalent at low pass)
        half_width_deg = min(2.0, max(0.5, (period_min / 90.0) * 1.0))

        while t < window_end:
            aos = t
            los = t + timedelta(minutes=period_min * 0.08)  # ~8% of orbital period visible
            # Max elevation: synthetic value based on distance from sub-satellite track
            max_el = round(max(5.0, min(90.0, 45.0 - abs(lat - (orbit.inclination_deg or 51.6)) * 0.5)), 1)
            footprint = _make_footprint(lon, lat, half_width_deg)

            sensor_map = {
                "SENTINEL": "MSI",
                "LANDSAT": "OLI",
                "ISS": "optical",
            }
            sensor_type: Optional[str] = None
            for prefix, stype in sensor_map.items():
                if satellite_id.upper().startswith(prefix):
                    sensor_type = stype
                    break

            passes.append(
                SatellitePass(
                    satellite_id=satellite_id,
                    norad_id=orbit.norad_id,
                    aos=aos,
                    los=los,
                    max_elevation_deg=max_el,
                    footprint_geojson=footprint,
                    sensor_type=sensor_type,
                    confidence=0.9,
                    source=_SOURCE,
                )
            )
            t += timedelta(minutes=period_min)

        return passes
