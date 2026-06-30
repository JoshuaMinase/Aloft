from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.dependencies import get_database
from app.services.audio_repository import get_audio, save_audio
from app.services.audio_service import synthesize_story_audio
from app.services.story_repository import get_story

router = APIRouter(prefix="/pois", tags=["audio"])


@router.post("/{source_id}/audio")
async def create_audio(
    source_id: str,
    language: str = "en",
    voice_id: str | None = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Response:
    resolved_voice = voice_id or get_settings().elevenlabs_voice_id

    existing = await get_audio(db, source_id, language, resolved_voice)
    if existing is not None and Path(existing.file_path).exists():
        return Response(content=Path(existing.file_path).read_bytes(), media_type="audio/mpeg")

    story = await get_story(db, source_id, language)
    if story is None:
        raise HTTPException(
            status_code=404,
            detail=f"No story found for source_id '{source_id}' in language '{language}'. Generate it first via POST /pois/{source_id}/story.",
        )

    audio_bytes = await synthesize_story_audio(
        story.text_content, language=language, voice_id=resolved_voice
    )
    asset = await save_audio(db, source_id, language, resolved_voice, audio_bytes)

    return Response(content=Path(asset.file_path).read_bytes(), media_type="audio/mpeg")
