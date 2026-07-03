from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_JWT_DEFAULT = "change-me-in-production-use-secrets-token-hex-32"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    app_contact_email: str = "CHANGE_ME@example.com"
    mongodb_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongodb_db_name: str = "aloft"
    
    # CORS configuration
    # In production, set this to specific origins like ["https://aloft.app", "https://www.aloft.app"]
    # Use ["*"] for development to allow all origins
    cors_allowed_origins: list[str] = ["*"]
    # None means "no Redis configured" -- rate limiting fails open (allows
    # the request) rather than blocking the whole app from working if
    # Redis isn't set up yet. See core/redis_client.py and
    # services/rate_limiter.py. Sessions (core/redis.py) also use this;
    # connect_to_redis() in that module becomes a no-op when it's None.
    redis_url: str | None = None

    # Per-IP request caps for the genuinely expensive/quota-limited
    # endpoints. These numbers exist specifically because of the tight
    # free-tier ceilings documented in the zero-cost plan -- AviationStack
    # caps around 100/month total, Groq caps around 30/min total. One
    # client retrying in a loop, or one bad actor, could otherwise burn
    # through a month's AviationStack quota in seconds.
    rate_limit_flight_lookups_per_hour: int = 10
    rate_limit_content_generation_per_hour: int = 20
    # Position updates are called every few seconds from the mobile app.
    # 600/min = 10 calls/sec — generous enough for any real polling interval.
    rate_limit_position_updates_per_minute: int = 600
    
    # Additional rate limits for expensive operations
    rate_limit_poi_discovery_per_hour: int = 30
    rate_limit_story_generation_per_hour: int = 50
    rate_limit_audio_synthesis_per_hour: int = 30
    rate_limit_downloads_per_hour: int = 10
    rate_limit_session_creation_per_hour: int = 20
    rate_limit_mixed_audio_per_hour: int = 15
    rate_limit_image_retrieval_per_hour: int = 40
    
    # Account lockout settings
    max_failed_login_attempts: int = 5
    account_lockout_duration_minutes: int = 30

    # Maximum concurrent Groq + ElevenLabs calls during batch content
    # generation (POST /routes/{route_key}/content).
    # 3 is a safe default for free-tier accounts:
    #   - Groq free tier: ~30 req/min total → 3 concurrent keeps us well under
    #   - ElevenLabs free tier: ~2 concurrent requests
    # Raise this if you're on a paid plan for faster batch generation.
    # Must be >= 1: asyncio.Semaphore(0) would permanently block all generation.
    content_generation_max_concurrent: int = Field(default=3, ge=1)

    # Content generation throttling -- tunable without code changes.
    # Groq free tier: ~30 req/min = 1 req/2s minimum.
    # Wikipedia free tier: generous but parallel bursts trigger 429s.
    content_inter_poi_delay_seconds: float = 3.0
    content_inter_image_delay_seconds: float = 1.0
    content_rate_limit_backoff_seconds: float = 60.0
    content_max_poi_retries: int = 3

    # How long a flight session lives in Redis before auto-expiring.
    # 12 hours covers any realistic flight duration with margin.
    session_ttl_seconds: int = 43200
    corridor_width_km: float = 100.0
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    elevenlabs_api_key: SecretStr | None = None
    # Default voice: "Bella" -- free tier voice for ElevenLabs.
    # Find other voice IDs at elevenlabs.io/voice-lab or GET /v1/voices.
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    audio_storage_dir: str = "./audio_storage"
    aviationstack_api_key: str | None = None

    # ---------------------------------------------------------------------------
    # Cloudflare R2 audio storage (optional — falls back to local disk when unset)
    # ---------------------------------------------------------------------------
    # R2 is S3-compatible. Get these values from:
    #   Cloudflare dashboard → R2 → Manage R2 API tokens
    #   Account ID: Cloudflare dashboard → right sidebar
    #
    # When all four R2 fields are set, audio files are stored in R2 and served
    # directly from there. When any field is missing, audio falls back to local
    # disk (audio_storage_dir). Local disk is fine for dev; R2 is required for
    # any deployment on ephemeral infrastructure (Render free tier, etc.).
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket_name: str | None = None

    @property
    def r2_configured(self) -> bool:
        """True when all four R2 credentials are present."""
        return all([
            self.r2_account_id,
            self.r2_access_key_id,
            self.r2_secret_access_key,
            self.r2_bucket_name,
        ])

    # ---------------------------------------------------------------------------
    # JWT authentication
    # ---------------------------------------------------------------------------
    # Generate a strong secret with: python -c "import secrets; print(secrets.token_hex(32))"
    # Must be set in production. The default is intentionally weak so local
    # dev works out of the box, but will raise an error at startup if
    # ENVIRONMENT=production and the default is still in place.
    jwt_secret_key: SecretStr = SecretStr(_JWT_DEFAULT)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        """Refuse to start in production with the default JWT secret.

        This turns a silent security hole into a loud startup crash so it
        can never slip through to a real deployment unnoticed.
        """
        if (
            self.environment.lower() == "production"
            and self.jwt_secret_key.get_secret_value() == _JWT_DEFAULT
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be changed from the default before running in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return self

    @model_validator(mode="after")
    def _check_production_cors(self) -> "Settings":
        """Refuse to start in production with wildcard CORS origins.

        Wildcard CORS allows any origin to access your API, which is a security risk.
        In production, specify your actual frontend domain(s).
        """
        if (
            self.environment.lower() == "production"
            and self.cors_allowed_origins == ["*"]
        ):
            raise ValueError(
                "CORS_ALLOWED_ORIGINS cannot be ['*'] in production. "
                "Set it to your actual frontend domain(s), e.g., ['https://aloft.app', 'https://www.aloft.app']"
            )
        return self

    # ---------------------------------------------------------------------------
    # POI source feature flags
    # ---------------------------------------------------------------------------
    # Wikipedia is the only live source today. Wikidata and GeoNames are
    # stubbed out (see app/clients/wikidata.py and app/clients/geonames.py)
    # and disabled by default -- enable them here when the implementations
    # are complete.
    #
    # Wikidata: structured metadata (coordinates, type classifications,
    #   description), pulls from the Wikidata Query Service (SPARQL).
    #   No API key required -- public endpoint.
    #   See: https://query.wikidata.org/
    #
    # GeoNames: populated-place and geographic feature names in 11 languages.
    #   Requires a free GeoNames account (username, not a key).
    #   See: https://www.geonames.org/export/web-services.html
    #   Free tier: 1,000 credits/hour, 30,000/day.
    poi_source_wikidata_enabled: bool = False
    poi_source_geonames_enabled: bool = False
    geonames_username: str | None = None
    # OSM Overpass: named physical features (peaks, ruins, airports, etc.)
    # No API key required. Public endpoint: overpass-api.de
    poi_source_overpass_enabled: bool = False

    # ---------------------------------------------------------------------------
    # Openverse image fallback
    # ---------------------------------------------------------------------------
    # When Wikipedia has no images for a POI, Openverse is queried as a fallback.
    # Anonymous access works (100 req/min) but registering a free client gets
    # 500 req/min. Register at: https://api.openverse.org/v1/auth_tokens/register/
    openverse_client_id: str | None = None
    openverse_client_secret: SecretStr | None = None

    # ---------------------------------------------------------------------------
    # OpenSky Network (optional — live aircraft position)
    # ---------------------------------------------------------------------------
    # OpenSky now requires OAuth2 client credentials (basic auth was retired).
    # Create an API client at https://opensky-network.org → Account → API Client.
    # Set both fields to get ~4,000 req/day. Leave unset for anonymous (~100 req/day).
    opensky_client_id: str | None = None
    opensky_client_secret: SecretStr | None = None

    # ---------------------------------------------------------------------------
    # Email service for password reset
    # ---------------------------------------------------------------------------
    # Resend (recommended): https://resend.com/ - Free tier: 3,000 emails/month
    # SendGrid (alternative): https://sendgrid.com/ - Free tier: 100 emails/day
    # FROM_EMAIL must be verified in your email service dashboard
    resend_api_key: SecretStr | None = None
    sendgrid_api_key: SecretStr | None = None
    from_email: str = "noreply@aloft.app"
    frontend_base_url: str = "http://localhost:3000"  # Your frontend URL for reset links


@lru_cache
def get_settings() -> Settings:
    return Settings()
