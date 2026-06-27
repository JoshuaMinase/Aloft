"""
Wraps Google Cloud Text-to-Speech's official async client.

Unlike every other client in this app, this is NOT a thin httpx wrapper.
Cloud TTS doesn't support simple API-key auth -- confirmed against
Google's own docs, which only describe OAuth2/Application Default
Credentials for this API (unlike its sibling Speech-to-Text API, which
does support a plain ?key= API key). Hand-rolling JWT signing and token
refresh ourselves would be real, unnecessary risk for something Google's
own google-auth library already does correctly -- so this uses their
official async client, the one deliberate exception to this project's
"thin httpx wrapper" pattern.

Credentials are picked up automatically from GOOGLE_APPLICATION_CREDENTIALS
via Application Default Credentials -- no code here reads that env var
directly, Google's library does it internally.
"""

from __future__ import annotations

import asyncio
import logging

from google.api_core import exceptions as google_exceptions
from google.cloud import texttospeech_v1

from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.tts")

# Transient/server-side failures worth a retry. NOT included:
# Unauthenticated, PermissionDenied, InvalidArgument -- a wrong voice name
# or missing credentials will fail identically every time.
_RETRYABLE_EXCEPTIONS = (
    google_exceptions.ServiceUnavailable,
    google_exceptions.InternalServerError,
    google_exceptions.ResourceExhausted,
    google_exceptions.DeadlineExceeded,
)
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0

_client: texttospeech_v1.TextToSpeechAsyncClient | None = None


class TtsClientError(Exception):
    """Raised when speech synthesis fails outright -- after retries are
    exhausted, or on a non-retryable error (bad voice name, missing
    credentials, invalid input).
    """


def _get_client() -> texttospeech_v1.TextToSpeechAsyncClient:
    """Created once and reused. This client manages its own gRPC channel
    and OAuth2 token refresh internally -- recreating it per call would
    throw that connection reuse and token caching away for nothing.
    """
    global _client
    if _client is None:
        _client = texttospeech_v1.TextToSpeechAsyncClient()
    return _client


async def synthesize_speech(
    text: str,
    *,
    language_code: str | None = None,
    voice_name: str | None = None,
) -> bytes:
    """Convert text to speech audio.

    Args:
        text: the text to narrate.
        language_code: BCP-47 code, e.g. "en-US". Defaults to
            settings.tts_language_code.
        voice_name: a specific Google voice name. Defaults to
            settings.tts_voice_name.

    Returns:
        Raw audio bytes (MP3-encoded).

    Raises:
        TtsClientError: missing/invalid credentials, an invalid voice or
            language, or retries exhausted on a transient failure.
    """
    settings = get_settings()
    request = texttospeech_v1.SynthesizeSpeechRequest(
        input=texttospeech_v1.SynthesisInput(text=text),
        voice=texttospeech_v1.VoiceSelectionParams(
            language_code=language_code or settings.tts_language_code,
            name=voice_name or settings.tts_voice_name,
        ),
        audio_config=texttospeech_v1.AudioConfig(
            audio_encoding=texttospeech_v1.AudioEncoding.MP3
        ),
    )

    client = _get_client()
    last_error: Exception | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.synthesize_speech(request=request)
        except _RETRYABLE_EXCEPTIONS as exc:
            last_error = exc
            logger.warning(
                "TTS synthesis retryable error, attempt %d/%d: %s",
                attempt, _MAX_ATTEMPTS, exc,
            )
        except google_exceptions.GoogleAPICallError as exc:
            raise TtsClientError(f"TTS synthesis failed (non-retryable): {exc}") from exc
        else:
            return response.audio_content

        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    raise TtsClientError(f"TTS synthesis failed after {_MAX_ATTEMPTS} attempts") from last_error
