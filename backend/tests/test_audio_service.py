from unittest.mock import AsyncMock

import pytest

from app.services.audio_service import synthesize_story_audio


@pytest.mark.asyncio
async def test_forwards_text_to_synthesize_speech(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Some text")

    mock_synth.assert_awaited_once_with("Some text", voice_id=None, http_client=None)


@pytest.mark.asyncio
async def test_passes_through_explicit_voice_id(monkeypatch):
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Text", voice_id="AZnzlk1XvdvUeBnXmlld")

    mock_synth.assert_awaited_once_with(
        "Text", voice_id="AZnzlk1XvdvUeBnXmlld", http_client=None
    )


@pytest.mark.asyncio
async def test_language_param_accepted_but_does_not_change_call(monkeypatch):
    """ElevenLabs is multilingual -- language doesn't affect the API call,
    but the parameter is kept for API compatibility with the router layer.
    """
    mock_synth = AsyncMock(return_value=b"audio bytes")
    monkeypatch.setattr("app.services.audio_service.synthesize_speech", mock_synth)

    await synthesize_story_audio("Some text", language="am")

    # Language is NOT forwarded -- ElevenLabs detects it from the text
    mock_synth.assert_awaited_once_with("Some text", voice_id=None, http_client=None)
