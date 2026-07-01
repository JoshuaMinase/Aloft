from unittest.mock import AsyncMock

import pytest

from app.services.audio_service import (
    _LANGUAGE_VOICE_DEFAULTS,
    get_voice_id_for_language,
    synthesize_story_audio,
)

_RACHEL = "21m00Tcm4TlvDq8ikWAM"  # default English voice


@pytest.mark.asyncio
async def test_forwards_text_to_synthesize_speech(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Some text")

    # Default English: resolves to Rachel (the global default)
    mock_synth.assert_awaited_once_with("Some text", voice_id=_RACHEL, http_client=None)


@pytest.mark.asyncio
async def test_passes_through_explicit_voice_id(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Text", voice_id="AZnzlk1XvdvUeBnXmlld")

    mock_synth.assert_awaited_once_with("Text", voice_id="AZnzlk1XvdvUeBnXmlld", http_client=None)


@pytest.mark.asyncio
async def test_language_selects_per_language_voice(monkeypatch):
    """Arabic and French should resolve to their per-language default voices."""
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("مرحباً", language="ar")

    expected_ar_voice = _LANGUAGE_VOICE_DEFAULTS["ar"]
    mock_synth.assert_awaited_once_with("مرحباً", voice_id=expected_ar_voice, http_client=None)


@pytest.mark.asyncio
async def test_unsupported_language_falls_back_to_rachel(monkeypatch):
    """A language not in _LANGUAGE_VOICE_DEFAULTS uses the Rachel fallback."""
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Hei verden", language="no")  # Norwegian -- not in defaults

    # Falls back to Rachel since "no" is not in _LANGUAGE_VOICE_DEFAULTS
    mock_synth.assert_awaited_once_with("Hei verden", voice_id=_RACHEL, http_client=None)


@pytest.mark.asyncio
async def test_explicit_voice_id_overrides_language_default(monkeypatch):
    """Explicit voice_id always wins over language-based lookup."""
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    custom_voice = "AZnzlk1XvdvUeBnXmlld"
    await synthesize_story_audio("مرحباً", language="ar", voice_id=custom_voice)

    # custom_voice wins despite language="ar"
    mock_synth.assert_awaited_once_with("مرحباً", voice_id=custom_voice, http_client=None)


def test_get_voice_id_for_language_arabic():
    assert get_voice_id_for_language("ar") == _LANGUAGE_VOICE_DEFAULTS["ar"]


def test_get_voice_id_for_language_french():
    assert get_voice_id_for_language("fr") == _LANGUAGE_VOICE_DEFAULTS["fr"]


def test_get_voice_id_for_language_english_returns_rachel():
    assert get_voice_id_for_language("en") == _RACHEL
