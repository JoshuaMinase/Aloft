from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    app_contact_email: str = "you@example.com"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "aloft"
    corridor_width_km: float = 100.0
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
