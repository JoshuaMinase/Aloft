"""
ElevenLabs text-to-speech client.

Uses ElevenLabs' /v1/text-to-speech/{voice_id} endpoint directly via
httpx -- the same thin-wrapper pattern as every other client in this app.
No credit card required on the free tier (10,000 chars/month).

Auth: a plain API key in the xi-api-key header. No OAuth, no service
account JSON, no Application Default Credentials -- just set
ELEVENLABS_API_KEY in your .env file.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.tts")

_BASE_URL = "https://api.elevenlabs.io"

# Transient server-side failures worth retrying.
# 401 (bad key) and 422 (bad voice ID / invalid input) are not retried --
# they will fail identically every time.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


class TtsClientError(Exception):
    """Raised when speech synthesis fails -- after retries are exhausted,
    or on a non-retryable error (bad API key, invalid voice ID).
    """


async def synthesize_speech(
    text: str,
    *,
    voice_id: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Convert text to MP3 audio bytes using ElevenLabs.

    Args:
        text: the text to narrate.
        voice_id: ElevenLabs voice ID. Defaults to settings.elevenlabs_voice_id.
            Find voice IDs at elevenlabs.io/voice-lab or via GET /v1/voices.
        http_client: optional injected httpx client (used in tests).
            If not provided, a short-lived client is created for this call.

    Returns:
        Raw MP3 audio bytes.

    Raises:
        TtsClientError: bad API key, invalid voice ID, or retries exhausted.
    """
    settings = get_settings()

    api_key = settings.elevenlabs_api_key
    if api_key is None:
        raise TtsClientError(
            "ELEVENLABS_API_KEY is not set. Add it to your .env file."
        )

    resolved_voice_id = voice_id or settings.elevenlabs_voice_id
    url = f"{_BASE_URL}/v1/text-to-speech/{resolved_voice_id}"

    headers = {
        "xi-api-key": api_key.get_secret_value(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "output_format": "mp3_44100_128",
    }

    should_close = http_client is None
    client = http_client or httpx.AsyncClient()
    last_error: Exception | None = None

    try:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "TTS request error, attempt %d/%d: %s", attempt, _MAX_ATTEMPTS, exc
                )
            else:
                if response.status_code == 200:
                    return response.content

                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = TtsClientError(
                        f"ElevenLabs returned {response.status_code}: {response.text}"
                    )
                    logger.warning(
                        "TTS retryable error %d, attempt %d/%d",
                        response.status_code, attempt, _MAX_ATTEMPTS,
                    )
                else:
                    # 401, 422, etc. -- won't succeed on retry
                    raise TtsClientError(
                        f"TTS synthesis failed (non-retryable): "
                        f"HTTP {response.status_code}: {response.text}"
                    )

            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    finally:
        if should_close:
            await client.aclose()

    raise TtsClientError(
        f"TTS synthesis failed after {_MAX_ATTEMPTS} attempts"
    ) from last_error
