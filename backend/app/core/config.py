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
    elevenlabs_api_key: SecretStr | None = None
    # Default voice: "Rachel" -- a clear, natural English narration voice.
    # Find other voice IDs at elevenlabs.io/voice-lab or GET /v1/voices.
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    audio_storage_dir: str = "./audio_storage"
    aviationstack_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
