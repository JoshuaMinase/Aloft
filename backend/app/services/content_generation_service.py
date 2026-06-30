from __future__ import annotations

import logging

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.clients.groq import GroqClientError
from app.clients.tts import TtsClientError
from app.clients.wikipedia import WikipediaClientError, get_images
from app.core.config import get_settings
from app.services.audio_repository import get_audio, save_audio
from app.services.audio_service import synthesize_story_audio
from app.services.poi_repository import get_poi, save_poi_images
from app.services.story_repository import get_story, save_story
from app.services.story_service import InsufficientFactsError, generate_story

logger = logging.getLogger("aloft.services.content_generation")


class PoiContentResult(BaseModel):
    poi_source_id: str
    story_ready: bool
    audio_ready: bool
    images_found: int
    error: str | None = None


async def generate_content_for_route(
    client: httpx.AsyncClient,
    db: AsyncIOMotorDatabase,
    poi_source_ids: list[str],
    language: str = "en",
) -> list[PoiContentResult]:
    results = []
    for source_id in poi_source_ids:
        results.append(await _generate_content_for_one_poi(client, db, source_id, language))
    return results


async def _generate_content_for_one_poi(
    client: httpx.AsyncClient, db: AsyncIOMotorDatabase, source_id: str, language: str
) -> PoiContentResult:
    poi = await get_poi(db, source_id)
    if poi is None:
        return PoiContentResult(
            poi_source_id=source_id, story_ready=False, audio_ready=False,
            images_found=0, error="POI was never discovered",
        )

    story_ready, audio_ready, error = await _ensure_story_and_audio(
        client, db, source_id, poi.name, language
    )

    images_found = 0
    try:
        images = await get_images(client, poi.name)
        await save_poi_images(db, source_id, [image.url for image in images])
        images_found = len(images)
    except WikipediaClientError as exc:
        logger.warning("Image fetch failed for %s: %s", source_id, exc)
        error = error or f"Image fetch failed: {exc}"

    return PoiContentResult(
        poi_source_id=source_id, story_ready=story_ready, audio_ready=audio_ready,
        images_found=images_found, error=error,
    )


async def _ensure_story_and_audio(
    client: httpx.AsyncClient,
    db: AsyncIOMotorDatabase,
    source_id: str,
    poi_name: str,
    language: str,
) -> tuple[bool, bool, str | None]:
    try:
        story = await get_story(db, source_id, language)
        if story is None:
            story = await generate_story(client, source_id, poi_name, language=language)
            await save_story(db, story)
    except InsufficientFactsError as exc:
        return False, False, f"Skipped: {exc}"
    except (WikipediaClientError, GroqClientError) as exc:
        logger.warning("Story generation failed for %s: %s", source_id, exc)
        return False, False, f"Story generation failed: {exc}"

    settings = get_settings()
    try:
        existing_audio = await get_audio(db, source_id, language, settings.elevenlabs_voice_id)
        if existing_audio is None:
            audio_bytes = await synthesize_story_audio(story.text_content, language=language)
            await save_audio(db, source_id, language, settings.elevenlabs_voice_id, audio_bytes)
    except TtsClientError as exc:
        logger.warning("Audio synthesis failed for %s: %s", source_id, exc)
        return True, False, f"Audio synthesis failed: {exc}"

    return True, True, None
