from __future__ import annotations

from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.models.audio import AudioAsset


def _file_path_for(poi_source_id: str, language: str, voice_name: str) -> Path:
    settings = get_settings()
    safe_id = poi_source_id.replace(":", "_")
    filename = f"{safe_id}__{language}__{voice_name}.mp3"
    return Path(settings.audio_storage_dir) / filename


async def save_audio(
    db: AsyncIOMotorDatabase,
    poi_source_id: str,
    language: str,
    voice_name: str,
    audio_bytes: bytes,
) -> AudioAsset:
    file_path = _file_path_for(poi_source_id, language, voice_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(audio_bytes)

    asset = AudioAsset(
        poi_source_id=poi_source_id,
        language=language,
        voice_name=voice_name,
        file_path=str(file_path),
    )
    await db.audio_assets.update_one(
        {"poi_source_id": poi_source_id, "language": language, "voice_name": voice_name},
        {"$set": asset.to_mongo_dict()},
        upsert=True,
    )
    return asset


async def get_audio(
    db: AsyncIOMotorDatabase, poi_source_id: str, language: str, voice_name: str
) -> AudioAsset | None:
    doc = await db.audio_assets.find_one(
        {"poi_source_id": poi_source_id, "language": language, "voice_name": voice_name}
    )
    if doc is None:
        return None
    doc.pop("_id", None)
    return AudioAsset(**doc)
