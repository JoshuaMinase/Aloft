from unittest.mock import AsyncMock

import pytest

from app.services.audio_service import synthesize_story_audio


@pytest.mark.asyncio
async def test_maps_internal_language_to_bcp47(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Some text", "am")

    mock_synth.assert_awaited_once_with("Some text", language_code="am-ET", voice_name=None)


@pytest.mark.asyncio
async def test_defaults_to_english(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Some text")

    mock_synth.assert_awaited_once_with("Some text", language_code="en-US", voice_name=None)


@pytest.mark.asyncio
async def test_falls_back_to_raw_code_for_unmapped_language(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Text", "xx")

    mock_synth.assert_awaited_once_with("Text", language_code="xx", voice_name=None)


@pytest.mark.asyncio
async def test_passes_through_explicit_voice_name(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Text", "en", voice_name="custom-voice")

    mock_synth.assert_awaited_once_with("Text", language_code="en-US", voice_name="custom-voice")
