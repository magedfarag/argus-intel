"""Operational-layer services — the approved live-source ingestion pattern.

ARCH-01 reference implementation.  Every domain layer that maintains typed
domain objects alongside the canonical EventStore MUST follow this pattern:

  1. A ``*LayerService`` singleton owns a connector instance and an in-memory
     store of typed domain objects.
  2. Routes import the accessor function (``get_*_service()``) and call it
     per-request; the singleton is returned immediately.
  3. ``initialize_operational_layers(settings)`` is called once in the app
     lifespan.  It switches connectors from stub → live when credentials are
     present and mode ≠ DEMO, then seeds the store.
  4. ``refresh()`` is called by Celery pollers on a schedule (and at startup
     via ``initialize_operational_layers``).
  5. Health is reported to ``SourceHealthService`` on every refresh attempt.

Demo-mode gating (ARCH-03):
  - In DEMO mode the service ALWAYS uses the stub connector regardless of
    whether live credentials are configured.
  - In STAGING / PRODUCTION, the service TRIES the live connector; if not
    available or not configured it falls back to the stub and logs a warning.
  - ``is_demo_mode`` property signals to routes whether to annotate responses.

JAM-01 decision (recorded here):
  No trustworthy free/open GNSS jamming source with a stable public API has
  been identified (GPSJam.org provides visualisation but no API; other sources
  are proprietary or classified).  ``JammingLayerService`` therefore remains
  permanently demo-only (``is_demo_mode`` always returns True) until an
  approved source is registered.  This implements JAM-03.
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import AppSettings

log = logging.getLogger(__name__)

# ── Seed TLE for the stub orbit store (moved here from src/api/orbits.py) ────
# Representative values; do NOT use for real mission planning.
_ORBIT_SEED_TLE = """\
ISS (ZARYA)
1 25544U 98067A   26094.50000000  .00002182  00000-0  40768-4 0  9994
2 25544  51.6469 253.1234 0006703 264.4623  95.5836 15.50000000439123
SENTINEL-2A
1 40697U 15028A   26094.50000000  .00000050  00000-0  17800-4 0  9991
2 40697  98.5683  62.2784 0001123  84.5271 275.6031 14.30820001562811
LANDSAT-9
1 49260U 21088A   26094.50000000  .00000032  00000-0  97100-5 0  9993
2 49260  98.2219 112.4721 0001456 100.1234 260.0000 14.57126001234567
"""

# Fixed reference timestamp for deterministic seeding of stub stores.
_STUB_REF_NOW = datetime(2026, 4, 4, 0, 0, 0, tzinfo=UTC)


# ── OrbitLayerService ─────────────────────────────────────────────────────────


class OrbitLayerService:
    """Singleton service managing the satellite orbit in-memory store.

    Backed by ``OrbitConnector`` (stub or live).  Routes delegate to this
    service instead of maintaining module-level globals.
    """

    def __init__(self) -> None:
        from src.connectors.orbit_connector import OrbitConnector

        self._lock = threading.Lock()
        self._stub = OrbitConnector()
        self._stub.connect()
        self._connector = self._stub
        self._demo_mode: bool = True
        self._orbits: dict = {}
        # Seed immediately so the service is usable before lifespan runs.
        self._seed_from_connector()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def initialize(
        self,
        *,
        demo_mode: bool,
        live_connector=None,
    ) -> None:
        """Called once in the app lifespan.

        Args:
            demo_mode:       True when ``APP_MODE == DEMO``.
            live_connector:  Optional live ``OrbitConnector`` subclass instance.
                             Ignored in demo mode.
        """
        self._demo_mode = demo_mode
        if not demo_mode and live_connector is not None:
            try:
                live_connector.connect()
                self._connector = live_connector
                log.info("OrbitLayerService: live connector registered (%s)", live_connector.connector_id)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "OrbitLayerService: live connector failed to connect (%s); using stub",
                    exc,
                )
                self._connector = self._stub
                self._demo_mode = True
        elif demo_mode:
            self._connector = self._stub
        else:
            log.info("OrbitLayerService: no live connector supplied; using stub in %s mode",
                     "demo" if demo_mode else "staging/production")

        self._seed_from_connector()

    def _seed_from_connector(self) -> None:
        """Populate the store from the active connector's seed TLE."""
        try:
            from src.connectors.orbit_connector import OrbitConnector
            if isinstance(self._connector, OrbitConnector):
                # Stub connector — ingest the representative TLE set.
                new_orbits = self._connector.ingest_orbits(_ORBIT_SEED_TLE)
                with self._lock:
                    for o in new_orbits:
                        self._orbits[o.satellite_id] = o
                self._report_health(healthy=True)
                log.debug("OrbitLayerService: seeded %d orbits from stub", len(new_orbits))
            else:
                # Live connector — call refresh() which handles live fetch.
                self.refresh()
        except Exception as exc:  # noqa: BLE001
            log.error("OrbitLayerService: seed failed — %s", exc)
            self._report_health(healthy=False, message=str(exc))

    def refresh(self, tle_text: str | None = None) -> None:
        """Refresh orbit store.  For live connectors, fetch fresh TLEs.

        Args:
            tle_text: Optional explicit TLE block for the stub (used by the
                      /ingest endpoint).  Live connectors fetch independently.
        """
        try:
            if tle_text:
                new_orbits = self._connector.ingest_orbits(tle_text)  # type: ignore[attr-defined]
            elif hasattr(self._connector, "fetch_all_tles"):
                new_orbits = self._connector.fetch_all_tles()
            else:
                new_orbits = self._connector.ingest_orbits(_ORBIT_SEED_TLE)  # type: ignore[attr-defined]

            with self._lock:
                for o in new_orbits:
                    self._orbits[o.satellite_id] = o

            self._ingest_canonical(new_orbits)
            self._report_health(healthy=True)
        except Exception as exc:  # noqa: BLE001
            log.error("OrbitLayerService.refresh failed: %s", exc)
            self._report_health(healthy=False, message=str(exc))

    # ── Store accessors ───────────────────────────────────────────────────

    def all_orbits(self) -> dict:
        with self._lock:
            return dict(self._orbits)

    def get_orbit(self, satellite_id: str):
        with self._lock:
            return self._orbits.get(satellite_id)

    def ingest_tle(self, tle_text: str) -> list:
        """Ingest a TLE block into the store; also push to canonical EventStore."""
        new_orbits = self._connector.ingest_orbits(tle_text)  # type: ignore[attr-defined]
        with self._lock:
            for o in new_orbits:
                self._orbits[o.satellite_id] = o
        self._ingest_canonical(new_orbits)
        return new_orbits

    def compute_passes(self, satellite_id: str, lon: float, lat: float, horizon_hours: int) -> list | None:
        """Return pass predictions or None if the satellite is unknown."""
        with self._lock:
            orbit = self._orbits.get(satellite_id)
        if orbit is None:
            return None
        # Keep stub connector in sync for pass computation.
        if hasattr(self._connector, "_orbits"):
            self._connector._orbits[satellite_id] = orbit
        return self._connector.compute_passes(satellite_id, lon, lat, horizon_hours)  # type: ignore[attr-defined]

    @property
    def is_demo_mode(self) -> bool:
        return self._demo_mode

    # ── Internals ─────────────────────────────────────────────────────────

    def _ingest_canonical(self, orbits: list) -> None:
        try:
            from src.connectors.orbit_connector import orbit_to_canonical_event
            from src.services.event_store import get_default_event_store
            events = [orbit_to_canonical_event(o) for o in orbits]
            get_default_event_store().ingest_batch(events)
        except Exception as exc:  # noqa: BLE001
            log.warning("OrbitLayerService: canonical ingest failed: %s", exc)

    def _report_health(self, *, healthy: bool, message: str = "") -> None:
        try:
            from src.services.source_health import get_health_service
            svc = get_health_service()
            cid = self._connector.connector_id
            dname = self._connector.display_name
            stype = self._connector.source_type
            if healthy:
                svc.record_success(cid, dname, stype)
            else:
                svc.record_error(cid, message or "refresh failed", dname, stype)
        except Exception:  # noqa: BLE001
            pass


# ── AirspaceLayerService ──────────────────────────────────────────────────────


class AirspaceLayerService:
    """Singleton service managing airspace restrictions and NOTAMs."""

    def __init__(self) -> None:
        from src.connectors.airspace_connector import AirspaceConnector

        self._lock = threading.Lock()
        self._stub = AirspaceConnector()
        self._stub.connect()
        self._connector = self._stub
        self._demo_mode: bool = True
        self._restrictions: dict = {}
        self._notams: dict = {}
        self._seed_from_connector()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def initialize(
        self,
        *,
        demo_mode: bool,
        live_connector=None,
    ) -> None:
        self._demo_mode = demo_mode
        if not demo_mode and live_connector is not None:
            try:
                live_connector.connect()
                self._connector = live_connector
                log.info("AirspaceLayerService: live connector registered (%s)", live_connector.connector_id)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "AirspaceLayerService: live connector failed (%s); using stub", exc
                )
                self._connector = self._stub
                self._demo_mode = True
        elif demo_mode:
            self._connector = self._stub
        self._seed_from_connector()

    def _seed_from_connector(self) -> None:
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            log.error("AirspaceLayerService: seed failed — %s", exc)

    def refresh(self) -> None:
        """Fetch fresh restrictions and NOTAMs from the active connector."""
        try:
            restrictions = self._connector.fetch_restrictions()  # type: ignore[attr-defined]
            notams = self._connector.fetch_notams()  # type: ignore[attr-defined]
            with self._lock:
                self._restrictions = {r.restriction_id: r for r in restrictions}
                self._notams = {n.notam_id: n for n in notams}
            self._ingest_canonical(restrictions, notams)
            self._report_health(healthy=True)
        except Exception as exc:  # noqa: BLE001
            log.error("AirspaceLayerService.refresh failed: %s", exc)
            self._report_health(healthy=False, message=str(exc))

    # ── Store accessors ───────────────────────────────────────────────────

    def all_restrictions(self) -> dict:
        with self._lock:
            return dict(self._restrictions)

    def get_restriction(self, restriction_id: str):
        with self._lock:
            return self._restrictions.get(restriction_id)

    def all_notams(self) -> dict:
        with self._lock:
            return dict(self._notams)

    def get_notam(self, notam_id: str):
        with self._lock:
            return self._notams.get(notam_id)

    @property
    def is_demo_mode(self) -> bool:
        return self._demo_mode

    # ── Internals ─────────────────────────────────────────────────────────

    def _ingest_canonical(self, restrictions: list, notams: list) -> None:
        try:
            from src.connectors.airspace_connector import (
                notam_to_canonical_event,
                restriction_to_canonical_event,
            )
            from src.services.event_store import get_default_event_store
            events = (
                [restriction_to_canonical_event(r) for r in restrictions]
                + [notam_to_canonical_event(n) for n in notams]
            )
            get_default_event_store().ingest_batch(events)
        except Exception as exc:  # noqa: BLE001
            log.warning("AirspaceLayerService: canonical ingest failed: %s", exc)

    def _report_health(self, *, healthy: bool, message: str = "") -> None:
        try:
            from src.services.source_health import get_health_service
            svc = get_health_service()
            cid = self._connector.connector_id
            dname = self._connector.display_name
            stype = self._connector.source_type
            if healthy:
                svc.record_success(cid, dname, stype)
            else:
                svc.record_error(cid, message or "refresh failed", dname, stype)
        except Exception:  # noqa: BLE001
            pass


# ── JammingLayerService ───────────────────────────────────────────────────────


class JammingLayerService:
    """Singleton service for GNSS jamming events.

    JAM-01 decision: no trustworthy free/open GNSS jamming API has been
    approved.  This service is permanently demo-only until an approved source
    is registered.  Live-connector support is stubbed out but intentionally
    unreachable — see JAM-02 / JAM-03 in the implementation plan.
    """

    # Connector_id used in health reports
    _CONNECTOR_ID = "gnss-monitor-derived"

    def __init__(self) -> None:
        from src.connectors.jamming_connector import JammingConnector

        self._lock = threading.Lock()
        self._connector = JammingConnector()
        self._connector.connect()
        self._store: dict = {}
        self._seed_from_connector()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def initialize(self, *, demo_mode: bool, live_connector=None) -> None:  # noqa: ARG002
        """Always demo-only regardless of mode until JAM-02 lands."""
        if live_connector is not None:
            log.warning(
                "JammingLayerService: live connector supplied but jamming remains demo-only "
                "(JAM-01 decision — no approved GNSS jamming source). Ignoring live connector."
            )
        self._seed_from_connector()

    def _seed_from_connector(self) -> None:
        try:
            w1_end = _STUB_REF_NOW
            w1_start = _STUB_REF_NOW - timedelta(days=30)
            events = self._connector.detect_jamming_events(w1_start, w1_end)  # type: ignore[attr-defined]
            if len(events) < 5:
                w2_start = _STUB_REF_NOW - timedelta(days=60)
                events.extend(self._connector.detect_jamming_events(w2_start, w1_start))  # type: ignore[attr-defined]
            with self._lock:
                for ev in events[:5]:
                    self._store[ev.jamming_id] = ev
            self._report_health(healthy=True)
        except Exception as exc:  # noqa: BLE001
            log.error("JammingLayerService: seed failed — %s", exc)
            self._report_health(healthy=False, message=str(exc))

    def refresh(self, start: datetime | None = None, end: datetime | None = None) -> list:
        """Generate deterministic events for a time window and append to store."""
        if start is None or end is None:
            end = datetime.now(UTC)
            start = end - timedelta(days=30)
        try:
            events = self._connector.detect_jamming_events(start, end)  # type: ignore[attr-defined]
            with self._lock:
                for ev in events:
                    self._store[ev.jamming_id] = ev
            self._report_health(healthy=True)
            return events
        except Exception as exc:  # noqa: BLE001
            log.error("JammingLayerService.refresh failed: %s", exc)
            self._report_health(healthy=False, message=str(exc))
            return []

    # ── Store accessors ───────────────────────────────────────────────────

    def all_events(self) -> dict:
        with self._lock:
            return dict(self._store)

    def get_event(self, jamming_id: str):
        with self._lock:
            return self._store.get(jamming_id)

    @property
    def is_demo_mode(self) -> bool:
        """Always True — jamming is permanently demo-only until JAM-02 lands."""
        return True

    # ── Internals ─────────────────────────────────────────────────────────

    def _report_health(self, *, healthy: bool, message: str = "") -> None:
        try:
            from src.services.source_health import get_health_service
            svc = get_health_service()
            if healthy:
                svc.record_success(self._CONNECTOR_ID, "GNSS Jamming Monitor (demo)", "derived")
            else:
                svc.record_error(self._CONNECTOR_ID, message or "refresh failed",
                                 "GNSS Jamming Monitor (demo)", "derived")
        except Exception:  # noqa: BLE001
            pass


# ── StrikeLayerService ────────────────────────────────────────────────────────


class StrikeLayerService:
    """Singleton service managing strike events and operator evidence links.

    Backed by ``StrikeConnector`` (stub) or an ACLED-derived live service.
    Evidence links are persisted in this service's own store (per-strike list).
    """

    def __init__(self) -> None:
        from src.connectors.strike_connector import StrikeConnector

        self._lock = threading.Lock()
        self._stub = StrikeConnector()
        self._stub.connect()
        self._connector = self._stub
        self._demo_mode: bool = True
        self._store: dict = {}
        self._evidence_store: dict[str, list] = {}
        self._seed_from_connector()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def initialize(
        self,
        *,
        demo_mode: bool,
        live_connector=None,
    ) -> None:
        self._demo_mode = demo_mode
        if not demo_mode and live_connector is not None:
            try:
                live_connector.connect()
                self._connector = live_connector
                log.info("StrikeLayerService: live connector registered (%s)", live_connector.connector_id)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "StrikeLayerService: live connector failed (%s); using stub", exc
                )
                self._connector = self._stub
                self._demo_mode = True
        elif demo_mode:
            self._connector = self._stub
        self._seed_from_connector()

    def _seed_from_connector(self) -> None:
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            log.error("StrikeLayerService: seed failed — %s", exc)

    def refresh(self) -> None:
        """Fetch fresh strike events from the active connector."""
        try:
            w1_end = _STUB_REF_NOW
            w1_start = _STUB_REF_NOW - timedelta(days=30)
            events = self._connector.fetch_strikes(w1_start, w1_end)  # type: ignore[attr-defined]
            if len(events) < 5:
                w2_start = _STUB_REF_NOW - timedelta(days=60)
                events.extend(self._connector.fetch_strikes(w2_start, w1_start))  # type: ignore[attr-defined]
            with self._lock:
                for ev in events[:5]:
                    if ev.strike_id not in self._store:
                        self._store[ev.strike_id] = ev
                        self._evidence_store[ev.strike_id] = []
            self._report_health(healthy=True)
        except Exception as exc:  # noqa: BLE001
            log.error("StrikeLayerService.refresh failed: %s", exc)
            self._report_health(healthy=False, message=str(exc))

    # ── Store accessors ───────────────────────────────────────────────────

    def all_strikes(self) -> dict:
        with self._lock:
            return dict(self._store)

    def get_strike(self, strike_id: str):
        with self._lock:
            return self._store.get(strike_id)

    def list_evidence(self, strike_id: str) -> list:
        with self._lock:
            return list(self._evidence_store.get(strike_id, []))

    def attach_evidence(self, strike_id: str, evidence) -> bool:
        """Attach an EvidenceLink to a strike.  Returns False if strike unknown."""
        with self._lock:
            if strike_id not in self._store:
                return False
            self._evidence_store.setdefault(strike_id, []).append(evidence)
            return True

    def fetch_range(self, start: datetime, end: datetime, region_bbox=None) -> list:
        """Query connector for strikes in a time range (used by pollers)."""
        return self._connector.fetch_strikes(start, end, region_bbox)  # type: ignore[attr-defined]

    @property
    def is_demo_mode(self) -> bool:
        return self._demo_mode

    # ── Internals ─────────────────────────────────────────────────────────

    def _report_health(self, *, healthy: bool, message: str = "") -> None:
        try:
            from src.services.source_health import get_health_service
            svc = get_health_service()
            cid = self._connector.connector_id
            dname = self._connector.display_name
            stype = self._connector.source_type
            if healthy:
                svc.record_success(cid, dname, stype)
            else:
                svc.record_error(cid, message or "refresh failed", dname, stype)
        except Exception:  # noqa: BLE001
            pass


# ── Module-level singletons ───────────────────────────────────────────────────

_orbit_svc: OrbitLayerService | None = None
_airspace_svc: AirspaceLayerService | None = None
_jamming_svc: JammingLayerService | None = None
_strike_svc: StrikeLayerService | None = None
_svc_lock = threading.Lock()


def get_orbit_service() -> OrbitLayerService:
    global _orbit_svc  # noqa: PLW0603
    if _orbit_svc is None:
        with _svc_lock:
            if _orbit_svc is None:
                _orbit_svc = OrbitLayerService()
    return _orbit_svc


def get_airspace_service() -> AirspaceLayerService:
    global _airspace_svc  # noqa: PLW0603
    if _airspace_svc is None:
        with _svc_lock:
            if _airspace_svc is None:
                _airspace_svc = AirspaceLayerService()
    return _airspace_svc


def get_jamming_service() -> JammingLayerService:
    global _jamming_svc  # noqa: PLW0603
    if _jamming_svc is None:
        with _svc_lock:
            if _jamming_svc is None:
                _jamming_svc = JammingLayerService()
    return _jamming_svc


def get_strike_service() -> StrikeLayerService:
    global _strike_svc  # noqa: PLW0603
    if _strike_svc is None:
        with _svc_lock:
            if _strike_svc is None:
                _strike_svc = StrikeLayerService()
    return _strike_svc


# ── Lifespan initialisation entry point ──────────────────────────────────────


def initialize_operational_layers(settings: "AppSettings") -> None:
    """Called once in ``app/main.py`` lifespan after settings are loaded.

    Resolves which connector to use for each domain layer based on the current
    ``APP_MODE`` and available credentials, then seeds each service store.
    """
    from app.config import AppMode

    demo_mode = settings.app_mode == AppMode.DEMO

    log.info(
        "Initialising operational layers | mode=%s demo=%s",
        settings.app_mode.value,
        demo_mode,
    )

    # Orbit — ORB-01: live connector in non-demo mode, graceful stub fallback.
    _orbit_live = None
    if not demo_mode:
        try:
            from src.connectors.celestrak_connector import CelestrakConnector
            _orbit_live = CelestrakConnector(
                timeout=getattr(settings, "celestrak_fetch_timeout_sec", 30)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ORB-01: CelestrakConnector unavailable, falling back to stub: %s", exc
            )
    get_orbit_service().initialize(demo_mode=demo_mode, live_connector=_orbit_live)

    # Airspace — AIR-01/AIR-03: attempt live FAA NOTAM connector in non-demo mode.
    _airspace_live = None
    if not demo_mode and getattr(settings, "faa_notam_client_id", None):
        try:
            from src.connectors.faa_notam_connector import FaaNotamConnector
            _airspace_live = FaaNotamConnector(
                client_id=settings.faa_notam_client_id,
                timeout=getattr(settings, "http_timeout_seconds", 30.0),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "AIR-03: FaaNotamConnector unavailable, falling back to stub: %s", exc
            )
    get_airspace_service().initialize(demo_mode=demo_mode, live_connector=_airspace_live)

    # Jamming — permanently demo-only (JAM-01 / JAM-03 decision).
    get_jamming_service().initialize(demo_mode=demo_mode, live_connector=None)

    # Strike — STR-02/STR-03: wire live ACLED connector in non-demo mode when configured.
    # ACLED data is free for non-commercial research only; AI/ML training and competitive
    # intelligence use requires a separate written ACLED agreement.  See
    # https://acleddata.com/terms-of-use/ before enabling in production.
    _strike_live = None
    if not demo_mode and settings.acled_is_configured():
        try:
            from src.connectors.acled_strike_connector import AcledStrikeConnector
            _strike_live = AcledStrikeConnector(
                email=settings.acled_email,
                password=settings.acled_password,
                token_url=settings.acled_token_url,
                api_url=settings.acled_api_url,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "STR-03: AcledStrikeConnector instantiation failed, using stub: %s", exc
            )
    get_strike_service().initialize(demo_mode=demo_mode, live_connector=_strike_live)

    log.info("Operational layers initialised")
