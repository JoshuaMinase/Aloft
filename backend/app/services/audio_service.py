from __future__ import annotations

from app.clients.tts import synthesize_speech

_TTS_LANGUAGE_CODES = {
    "en": "en-US",
    "am": "am-ET",
    "ar": "ar-XA",
    "fr": "fr-FR",
}


async def synthesize_story_audio(
    text: str,
    language: str = "en",
    voice_name: str | None = None,
) -> bytes:
    tts_language_code = _TTS_LANGUAGE_CODES.get(language, language)
    return await synthesize_speech(text, language_code=tts_language_code, voice_name=voice_name)
