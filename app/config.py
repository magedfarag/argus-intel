"""Application configuration using pydantic-settings.

All settings are read from environment variables or a .env file in the
working directory.  The flat model ensures that .env values are correctly
loaded for every field — nested BaseSettings subclasses owned by a parent
BaseSettings do NOT inherit the parent's env_file source, which would cause
silent misses when credentials live only in .env.

Env-var ↔ field mapping (case-insensitive):
    SENTINEL2_CLIENT_ID      → sentinel2_client_id
    SENTINEL2_CLIENT_SECRET  → sentinel2_client_secret
    REDIS_URL                → redis_url
    APP_MODE                 → app_mode
    … etc.

Copy .env.example → .env and fill in values before running.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    """Application operating mode.
    
    - DEMO: Always use DemoProvider (for testing, no live data)
    - STAGING: Real providers with demo fallback (safe default)
    - PRODUCTION: Real providers only (no demo fallback, fail-fast)
    """
    DEMO = "demo"
    STAGING = "staging"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Root application settings — flat model, all fields map to env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Case-insensitive matching: REDIS_URL == redis_url
        case_sensitive=False,
    )

    # ── App behaviour ────────────────────────────────────────────────────────
    app_mode: AppMode = Field(
        default=AppMode.STAGING,
        description="Operating mode: demo (always demo), staging (sentinel→landsat→demo), production (sentinel→landsat only)",
    )

    # ── CORS / Security ──────────────────────────────────────────────────────
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000",
        description="Comma-separated list of allowed CORS origins. Defaults to localhost for development.",
    )
    api_key: str = Field(
        default="",
        description=(
            "API key for authentication (Bearer token, ?api_key query, or api_key cookie). "
            "If empty, authentication is disabled (insecure dev mode). "
            "For production, set to a strong random value (e.g., openssl rand -hex 32)."
        ),
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")

    # ── Sentinel-2 (Copernicus Data Space Ecosystem) ─────────────────────────
    # Register at https://dataspace.copernicus.eu to obtain credentials.
    sentinel2_client_id: str = Field(default="")
    sentinel2_client_secret: str = Field(default="")
    sentinel2_token_url: str = Field(
        default="https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    sentinel2_stac_url: str = Field(
        default="https://catalogue.dataspace.copernicus.eu/stac"
    )

    # ── Landsat (USGS LandsatLook STAC) ──────────────────────────────────────
    # STAC search is publicly accessible without credentials.
    # Provide USGS ERS username/password only if M2M bulk download is required.
    landsat_username: str = Field(default="")
    landsat_password: str = Field(default="")
    landsat_stac_url: str = Field(
        default="https://landsatlook.usgs.gov/stac-server"
    )

    # ── Maxar (SecureWatch / Open Data) ──────────────────────────────────────
    # Commercial high-resolution (0.3-0.5 m).  Requires SecureWatch subscription.
    maxar_api_key: str = Field(default="")
    maxar_stac_url: str = Field(
        default="https://api.maxar.com/discovery/v1"
    )

    # ── Planet (PlanetScope / SkySat) ────────────────────────────────────────
    # Commercial daily revisit (3-5 m PlanetScope, 0.5 m SkySat).
    planet_api_key: str = Field(default="")
    planet_api_url: str = Field(
        default="https://api.planet.com/data/v1"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="",
        description="Redis connection URL. Required for Celery + persistent job cache.",
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="",
        description="PostgreSQL connection URL for persistent job history (e.g. postgresql+psycopg2://user:pass@host/db).",
    )

    # ── Celery ────────────────────────────────────────────────────────────────
    # Defaults fall back to redis_url when not explicitly set (see properties).
    celery_broker_url: str = Field(default="")
    celery_result_backend: str = Field(default="")

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_ttl_seconds: int = Field(
        default=3600, description="TTL for cached analysis results (seconds)"
    )
    cache_max_entries: int = Field(
        default=256, description="Max entries for in-memory TTLCache fallback"
    )

    # ── HTTP client ───────────────────────────────────────────────────────────
    http_timeout_seconds: float = Field(default=30.0)
    http_max_retries: int = Field(default=3)

    # ── Circuit breaker ───────────────────────────────────────────────────────
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_recovery_timeout: int = Field(
        default=60, description="Seconds before half-open probe after circuit opens"
    )

    # ── Analysis pipeline ─────────────────────────────────────────────────────
    default_cloud_threshold: float = Field(
        default=20.0, description="Max cloud cover % to accept a scene"
    )
    async_area_threshold_km2: float = Field(
        default=25.0,
        description="AOI areas above this threshold are automatically sent to async queue",
    )
    raster_temp_dir: Optional[str] = Field(
        default=None,
        description="Temp dir for raster downloads. Defaults to system temp.",
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    # ── Convenience helpers ───────────────────────────────────────────────────

    def get_cors_origins(self) -> list[str]:
        """Parse allowed_origins string into a list of URLs."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def redis_available(self) -> bool:
        """Return True when a Redis URL has been configured."""
        return bool(self.redis_url)

    def effective_celery_broker(self) -> str:
        """Celery broker URL, falling back to redis_url."""
        return self.celery_broker_url or self.redis_url

    def effective_celery_backend(self) -> str:
        """Celery result backend URL, falling back to redis_url."""
        return self.celery_result_backend or self.redis_url

    def sentinel2_is_configured(self) -> bool:
        """Return True when Sentinel-2 OAuth2 credentials are present."""
        return bool(self.sentinel2_client_id and self.sentinel2_client_secret)

    def landsat_is_configured(self) -> bool:
        """Landsat STAC search is publicly accessible; always returns True."""
        return True

    def maxar_is_configured(self) -> bool:
        """Return True when Maxar API key is present."""
        return bool(self.maxar_api_key)

    def planet_is_configured(self) -> bool:
        """Return True when Planet API key is present."""
        return bool(self.planet_api_key)

    # ── V2 connector settings (P0-2.5) ───────────────────────────────────────

    # Object storage (MinIO for local dev; S3-compatible for production)
    object_storage_endpoint: str = Field(
        default="", description="S3-compatible endpoint URL, e.g. http://localhost:9000"
    )
    object_storage_bucket: str = Field(
        default="geoint-raw", description="Bucket for raw payloads and artifacts"
    )
    object_storage_access_key: str = Field(default="")
    object_storage_secret_key: str = Field(default="")

    # AISStream (WebSocket maritime tracking)
    aisstream_api_key: str = Field(
        default="", description="AISStream API key; register at https://aisstream.io"
    )
    aisstream_ws_url: str = Field(
        default="wss://stream.aisstream.io/v0/stream",
        description="AISStream WebSocket endpoint",
    )

    # OpenSky Network (aviation, non-commercial restrictions)
    opensky_username: str = Field(default="")
    opensky_password: str = Field(default="")
    opensky_api_url: str = Field(
        default="https://opensky-network.org/api",
        description="OpenSky REST API base URL",
    )

    # GDELT 2.0 (contextual news events)
    gdelt_base_url: str = Field(
        default="https://api.gdeltproject.org/api/v2",
        description="GDELT DOC 2.0 API base URL",
    )

    # Earth Search (Element 84) — free STAC, no auth
    earth_search_stac_url: str = Field(
        default="https://earth-search.aws.element84.com/v1",
        description="Element 84 Earth Search STAC endpoint",
    )

    # Microsoft Planetary Computer
    planetary_computer_stac_url: str = Field(
        default="https://planetarycomputer.microsoft.com/api/stac/v1",
        description="Microsoft Planetary Computer STAC endpoint",
    )
    planetary_computer_token: str = Field(
        default="", description="Optional Planetary Computer subscription key"
    )

    # ── P5: Production Hardening settings ────────────────────────────────────

    # P5-1: Caching TTLs (seconds)
    cache_ttl_timeline_seconds: int = Field(
        default=300, description="TTL for hot timeline window cache entries (P5-1.1)"
    )
    cache_ttl_stac_seconds: int = Field(
        default=900, description="TTL for STAC search result cache entries (P5-1.2)"
    )
    cache_ttl_playback_seconds: int = Field(
        default=120, description="TTL for playback query result cache entries (P5-1.3)"
    )
    cache_ttl_source_health_seconds: int = Field(
        default=60, description="TTL for source health snapshot cache entries (P5-1.4)"
    )

    # P5-1.5: Server-side density reduction threshold
    events_density_threshold: int = Field(
        default=500,
        description=(
            "When an event search returns more than this many results, "
            "apply server-side subsampling before returning the response."
        ),
    )
    events_density_max_results: int = Field(
        default=200,
        description="Maximum results to return after density reduction.",
    )

    # P5-2.4: Per-provider hourly request caps (0 = unlimited)
    aisstream_max_requests_per_hour: int = Field(
        default=0, description="Hard cap for AISStream hourly calls (0 = unlimited)"
    )
    opensky_max_requests_per_hour: int = Field(
        default=60, description="OpenSky non-commercial friendly rate cap (1/min)"
    )
    planet_max_requests_per_hour: int = Field(
        default=200, description="Planet Labs API hourly cap (paid tier)"
    )

    # P5-3.2: Freshness SLA defaults (minutes)
    sla_gdelt_max_age_minutes: int = Field(default=30)
    sla_opensky_max_age_minutes: int = Field(default=5)
    sla_aisstream_max_age_minutes: int = Field(default=5)
    sla_sentinel2_max_age_minutes: int = Field(default=60)
    sla_landsat_max_age_minutes: int = Field(default=120)

    # P5-4.4: Automated data retention enforcement
    retention_enforcement_enabled: bool = Field(
        default=True, description="Enable automatic telemetry retention enforcement via Celery beat"
    )
    retention_enforcement_interval_seconds: int = Field(
        default=3600, description="Celery beat interval for retention enforcement (seconds)"
    )

    def aisstream_is_configured(self) -> bool:
        return bool(self.aisstream_api_key)

    def opensky_is_configured(self) -> bool:
        return bool(self.opensky_username and self.opensky_password)

    def object_storage_is_configured(self) -> bool:
        return bool(self.object_storage_endpoint and self.object_storage_access_key)

    # ── RapidAPI AIS ──────────────────────────────────────────────────────────
    rapid_api_key: str = Field(
        default="", description="RapidAPI subscription key (shared by maritime APIs)"
    )
    rapid_api_host: str = Field(
        default="ais-hub.p.rapidapi.com",
        description="X-RapidAPI-Host header for the generic AIS endpoint",
    )
    rapid_api_poll_interval: int = Field(
        default=300, description="Polling interval in seconds for RapidAPI AIS"
    )
    rapid_api_south: float = Field(default=24.5, description="Default bbox south latitude")
    rapid_api_west: float = Field(default=55.5, description="Default bbox west longitude")
    rapid_api_north: float = Field(default=27.5, description="Default bbox north latitude")
    rapid_api_east: float = Field(default=60.5, description="Default bbox east longitude")

    # ── VesselData API (vessel-data.p.rapidapi.com) ───────────────────────────
    vessel_data_api_key: str = Field(
        default="", description="RapidAPI key for vessel-data.p.rapidapi.com"
    )
    vessel_data_poll_interval: int = Field(
        default=60, description="Polling interval in seconds for VesselData"
    )
    vessel_data_south: float = Field(default=24.5, description="Default bbox south latitude")
    vessel_data_west: float = Field(default=55.5, description="Default bbox west longitude")
    vessel_data_north: float = Field(default=27.5, description="Default bbox north latitude")
    vessel_data_east: float = Field(default=60.5, description="Default bbox east longitude")

    def rapid_api_is_configured(self) -> bool:
        return bool(self.rapid_api_key)

    def vessel_data_is_configured(self) -> bool:
        return bool(self.vessel_data_api_key)

    # ── Phase 6 Auth / RBAC ───────────────────────────────────────────────────
    jwt_secret: str = Field(
        default="",
        description=(
            "Secret for signing HMAC-SHA256 role tokens. "
            "Defaults to api_key value if unset. "
            "Set to a strong random value in production (e.g. openssl rand -hex 32)."
        ),
    )
    admin_api_key: str = Field(
        default="",
        description="Raw API key granting admin role. Checked after JWT decoding.",
    )
    operator_api_key: str = Field(
        default="",
        description="Raw API key granting operator role. Checked after JWT decoding.",
    )
    analyst_api_key: str = Field(
        default="",
        description=(
            "Raw API key granting analyst role. "
            "Falls back to api_key if unset (backward compat)."
        ),
    )

    # ── Phase 6 Track B: Cost guardrails ──────────────────────────────────────
    max_briefings_per_hour_per_user: int = Field(
        default=10,
        description="Max briefing generations per user per hour (0 = unlimited).",
    )
    max_evidence_packs_per_hour_per_user: int = Field(
        default=20,
        description="Max evidence pack generations per user per hour (0 = unlimited).",
    )
    max_export_size_mb: int = Field(
        default=50,
        description="Maximum export payload size in megabytes.",
    )


@dataclass(frozen=True)
class Sentinel2Config:
    """Immutable view of Sentinel-2 provider settings."""

    client_id: str
    client_secret: str
    token_url: str
    stac_url: str

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True)
class LandsatConfig:
    """Immutable view of Landsat provider settings."""

    username: str
    password: str
    stac_url: str

    def is_configured(self) -> bool:
        # Search requires no auth; M2M download does.
        return True


def build_sentinel2_config(s: AppSettings) -> Sentinel2Config:
    return Sentinel2Config(
        client_id=s.sentinel2_client_id,
        client_secret=s.sentinel2_client_secret,
        token_url=s.sentinel2_token_url,
        stac_url=s.sentinel2_stac_url,
    )


def build_landsat_config(s: AppSettings) -> LandsatConfig:
    return LandsatConfig(
        username=s.landsat_username,
        password=s.landsat_password,
        stac_url=s.landsat_stac_url,
    )


# ── Singleton accessor ────────────────────────────────────────────────────────

_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """Return the cached singleton AppSettings instance.

    On first call, pydantic-settings reads .env (if present) then os.environ.
    Subsequent calls return the already-built instance.
    """
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings

