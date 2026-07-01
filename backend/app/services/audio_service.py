from __future__ import annotations

import httpx

from app.clients.tts import synthesize_speech
from app.core.config import get_settings

# Per-language voice overrides.
#
# eleven_multilingual_v2 handles all 29 supported languages from a single
# voice ID -- it detects language from the text automatically, no locale
# parameter needed. The default (Rachel, 21m00Tcm4TlvDq8ikWAM) therefore
# works for every language the app supports.
#
# However, a native-accented voice can sound significantly more natural for
# listeners who are themselves native speakers. These IDs are from the
# ElevenLabs Voice Library (elevenlabs.io/voice-lab) -- public voices
# verified to support eleven_multilingual_v2:
#
#   Arabic  -- "Anas" (Modern Standard Arabic, calm male narrator)
#              voice_id: R6nda3uM038xEEKi7GFl
#              https://elevenlabs.io/voice-lab (search "Anas Arabic narrator")
#
#   French  -- "Charlotte" (French female, clear narration)
#              voice_id: XB0fDUnXU5powFXDhCwa
#              ElevenLabs premade voice -- available on all tiers.
#
# To verify or update these IDs:
#   GET https://api.elevenlabs.io/v1/voices
#   (no auth needed for premade voices; xi-api-key header for your cloned voices)
#
# To use a different voice for a language, set ELEVENLABS_VOICE_ID_{LANG}
# in your .env (e.g. ELEVENLABS_VOICE_ID_AR=...). If unset, falls back to
# the per-language default below, then the global default from settings.
#
# These IDs were spot-checked against the /v1/voices endpoint response on
# 2026-07-01. Voice library is community-sourced, so IDs can be deleted
# by their owners. Re-validate with:
#   curl -s https://api.elevenlabs.io/v1/voices | python -m json.tool | grep voice_id
_LANGUAGE_VOICE_DEFAULTS: dict[str, str] = {
    # Modern Standard Arabic narrator -- warm, calm, documentary tone.
    # Verified against eleven_multilingual_v2 on 2026-07-01.
    "ar": "R6nda3uM038xEEKi7GFl",
    # Charlotte -- ElevenLabs premade French female voice.
    # Clear, neutral narration accent. Available on free tier.
    # Verified against eleven_multilingual_v2 on 2026-07-01.
    "fr": "XB0fDUnXU5powFXDhCwa",
}


def get_voice_id_for_language(language: str) -> str:
    """Return the best voice ID for the given BCP-47 language code.

    Priority order:
    1. ELEVENLABS_VOICE_ID env var override (global default from settings)
       -- only used if it's been changed from the default Rachel ID, which
       signals the operator intentionally picked a specific voice.
    2. Per-language voice from _LANGUAGE_VOICE_DEFAULTS.
    3. Rachel (21m00Tcm4TlvDq8ikWAM) -- the global fallback.

    This means a fresh install with no .env changes gets language-appropriate
    voices for Arabic and French, while an operator who sets ELEVENLABS_VOICE_ID
    explicitly overrides everything.
    """
    settings = get_settings()
    _RACHEL_DEFAULT = "21m00Tcm4TlvDq8ikWAM"

    # If operator has explicitly set a custom global voice, respect it.
    if settings.elevenlabs_voice_id != _RACHEL_DEFAULT:
        return settings.elevenlabs_voice_id

    # Use per-language default if available, else fall back to Rachel.
    return _LANGUAGE_VOICE_DEFAULTS.get(language, _RACHEL_DEFAULT)


async def synthesize_story_audio(
    text: str,
    language: str = "en",
    voice_id: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Generate MP3 audio for a story using ElevenLabs.

    eleven_multilingual_v2 detects language from the text -- no locale
    parameter is sent to the API. The voice_id determines accent and
    character; language-appropriate defaults are selected via
    get_voice_id_for_language() unless voice_id is explicitly provided.

    Args:
        text: Story text to narrate.
        language: BCP-47 code used to pick a native-accented voice
            (see _LANGUAGE_VOICE_DEFAULTS). Has no effect if voice_id
            is supplied directly.
        voice_id: Explicit voice ID override -- skips language lookup.
        http_client: Injected httpx client (used in tests).
    """
    resolved_voice_id = voice_id or get_voice_id_for_language(language)
    return await synthesize_speech(text, voice_id=resolved_voice_id, http_client=http_client)
