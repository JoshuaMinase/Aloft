"""
Processes content generation jobs from the Redis queue, one POI at a
time with deliberate delays between each request.

This runs as a separate async task started in main.py's lifespan --
not a separate process, just a background asyncio task that picks up
jobs while the main API handles requests normally.

Rate limit strategy:
- Groq:     1 story every 3 seconds (stays under 30/min)
- Wikipedia: 1 image fetch every 1 second (avoids 429 bursts)
- On 429:   back off 60 seconds, retry up to 3 times
- On other error: log, mark POI failed, move to next POI
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.groq import GroqClientError
from app.clients.wikipedia import WikipediaClientError, get_images
from app.services.audio_repository import get_audio, save_audio
from app.services.audio_service import get_voice_id_for_language, synthesize_story_audio
from app.services.content_job_service import (
    INTER_IMAGE_DELAY_SECONDS,
    INTER_POI_DELAY_SECONDS,
    RATE_LIMIT_BACKOFF_SECONDS,
    MAX_POI_RETRIES,
    JobStatus,
    get_job_status,
    update_job_progress,
)
from app.clients.tts import TtsClientError
from app.services.poi_repository import get_poi, save_poi_images
from app.services.story_repository import get_story, save_story
from app.services.story_service import InsufficientFactsError, generate_story

logger = logging.getLogger("aloft.services.content_worker")


async def run_worker(
    redis_client: redis.Redis,
    db: AsyncIOMotorDatabase,
    http_client: httpx.AsyncClient,
) -> None:
    """Main worker loop. Runs forever, picks up jobs from the queue.
    Called once from main.py lifespan as a background asyncio task.
    """
    logger.info("Content worker started")
    while True:
        try:
            # BRPOP blocks up to 5 seconds waiting for a job --
            # returns None if nothing arrives, loops back and waits again.
            result = await redis_client.brpop("queue:content", timeout=5)
            if result is None:
                continue

            _, job_id = result
            job_id = job_id.decode() if isinstance(job_id, bytes) else job_id
            await _process_job(redis_client, db, http_client, job_id)

        except asyncio.CancelledError:
            logger.info("Content worker shutting down")
            break
        except Exception:
            logger.exception("Unexpected error in content worker, continuing")
            await asyncio.sleep(5)


async def _process_job(
    redis_client: redis.Redis,
    db: AsyncIOMotorDatabase,
    http_client: httpx.AsyncClient,
    job_id: str,
) -> None:
    job = await get_job_status(redis_client, job_id)
    if job is None:
        logger.warning("Job %s not found in Redis", job_id)
        return

    poi_source_ids = job["poi_source_ids"]
    language = job["language"]
    completed = 0
    failed = 0

    await update_job_progress(redis_client, job_id, 0, 0, JobStatus.PROCESSING)
    logger.info("Processing job %s: %d POIs, language=%s", job_id, len(poi_source_ids), language)

    for source_id in poi_source_ids:
        success = await _process_one_poi_with_retry(
            http_client, db, redis_client, job_id,
            source_id, language, completed, failed,
        )
        if success:
            completed += 1
        else:
            failed += 1

        await update_job_progress(redis_client, job_id, completed, failed, JobStatus.PROCESSING)

        # Deliberate delay between POIs -- this is the key fix.
        # Without this, 200 POIs fire 200 Groq requests instantly → 429s.
        await asyncio.sleep(INTER_POI_DELAY_SECONDS)

    # Job is COMPLETED even if some POIs failed -- we processed everything we could
    final_status = JobStatus.COMPLETED
    await update_job_progress(redis_client, job_id, completed, failed, final_status)
    logger.info("Job %s done: %d completed, %d failed", job_id, completed, failed)


async def _process_one_poi_with_retry(
    http_client: httpx.AsyncClient,
    db: AsyncIOMotorDatabase,
    redis_client: redis.Redis,
    job_id: str,
    source_id: str,
    language: str,
    completed: int,
    failed: int,
) -> bool:
    """Process one POI with up to MAX_POI_RETRIES retries on rate limits."""
    for attempt in range(1, MAX_POI_RETRIES + 1):
        try:
            await _process_one_poi(http_client, db, source_id, language)
            return True
        except GroqClientError as exc:
            error_str = str(exc)
            if "429" in error_str or "rate" in error_str.lower():
                logger.warning(
                    "Groq rate limit on %s attempt %d/%d -- backing off %ds",
                    source_id, attempt, MAX_POI_RETRIES, RATE_LIMIT_BACKOFF_SECONDS,
                )
                if attempt < MAX_POI_RETRIES:
                    await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                    continue
            logger.warning("Groq error on %s (non-retryable): %s", source_id, exc)
            return False
        except WikipediaClientError as exc:
            error_str = str(exc)
            if "429" in error_str:
                logger.warning("Wikipedia rate limit on %s -- backing off", source_id)
                if attempt < MAX_POI_RETRIES:
                    await asyncio.sleep(30.0)
                    continue
            logger.warning("Wikipedia error on %s: %s", source_id, exc)
            return False
        except InsufficientFactsError:
            # Not worth retrying -- no Wikipedia article means no article.
            return False
        except Exception as exc:
            logger.warning("Unexpected error on %s: %s", source_id, exc)
            return False
    return False


async def _process_one_poi(
    http_client: httpx.AsyncClient,
    db: AsyncIOMotorDatabase,
    source_id: str,
    language: str,
) -> None:
    """Generate story + audio + images for one POI if not already cached."""
    poi = await get_poi(db, source_id)
    if poi is None:
        return

    # Story -- skip if already exists
    story = await get_story(db, source_id, language)
    if story is None:
        story = await generate_story(http_client, source_id, poi.name, language=language)
        await save_story(db, story)

    # Audio -- skip if already exists
    voice_id = get_voice_id_for_language(language)
    existing_audio = await get_audio(db, source_id, language, voice_id)
    if existing_audio is None:
        try:
            audio_bytes = await synthesize_story_audio(
                story.text_content, language=language, http_client=http_client
            )
            await save_audio(db, source_id, language, voice_id, audio_bytes)
        except TtsClientError as exc:
            logger.warning("TTS failed for %s: %s -- story saved, no audio", source_id, exc)

    # Images -- with deliberate delay, separate from story generation
    await asyncio.sleep(INTER_IMAGE_DELAY_SECONDS)
    # Re-fetch POI to check if images were added since we started
    poi = await get_poi(db, source_id)
    if poi is not None and not poi.image_refs:
        images = await get_images(http_client, poi.name)
        await save_poi_images(db, source_id, [img.url for img in images])
