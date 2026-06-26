"""
Centralized settings, read once from environment variables.

Every service/client should pull config from HERE, not from os.environ
scattered around the codebase.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    # Several external APIs (Wikipedia included) throttle or block requests
    # that don't identify the calling app and a contact point. This goes
    # into the User-Agent header on every outbound API call.
    app_contact_email: str = "you@example.com"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "aloft"

    corridor_width_km: float = 100.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
