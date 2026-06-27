from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    app_contact_email: str = "you@example.com"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "aloft"
    corridor_width_km: float = 100.0
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama3-70b-8192"
    tts_language_code: str = "en-US"
    tts_voice_name: str = "en-US-Wavenet-D"


@lru_cache
def get_settings() -> Settings:
    return Settings()
