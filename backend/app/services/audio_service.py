from __future__ import annotations

import httpx

from app.clients.tts import synthesize_speech


async def synthesize_story_audio(
    text: str,
    language: str = "en",
    voice_id: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Generate MP3 audio for a story using ElevenLabs.

    ElevenLabs voices are multilingual -- the same voice ID works across
    languages, so there's no BCP-47 mapping needed here.  Pass a
    specific voice_id to override the default set in settings.

    language is accepted for API compatibility but not forwarded to
    ElevenLabs (the model handles language automatically from the text).
    """
    return await synthesize_speech(text, voice_id=voice_id, http_client=http_client)
