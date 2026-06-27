"""
Tests for the TTS client. Mocks at the _get_client() level since this
isn't an httpx-based client -- respx only intercepts httpx traffic,
not Google's gRPC-based client library.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.api_core import exceptions as google_exceptions

from app.clients.tts import TtsClientError, synthesize_speech


def _fake_response(audio_content: bytes = b"fake-mp3-bytes") -> MagicMock:
    response = MagicMock()
    response.audio_content = audio_content
    return response


@pytest.fixture(autouse=True)
def no_real_sleep():
    with patch("app.clients.tts.asyncio.sleep", new=AsyncMock()):
        yield


@pytest.fixture(autouse=True)
def reset_client_singleton():
    """_get_client() caches a module-level client -- reset it between
    tests so one test's mock doesn't leak into the next.
    """
    import app.clients.tts as tts_module

    tts_module._client = None
    yield
    tts_module._client = None


def _mock_client(monkeypatch, synthesize_speech_mock: AsyncMock) -> None:
    fake_client = MagicMock()
    fake_client.synthesize_speech = synthesize_speech_mock
    monkeypatch.setattr("app.clients.tts._get_client", lambda: fake_client)


@pytest.mark.asyncio
async def test_synthesize_speech_returns_audio_bytes(monkeypatch):
    _mock_client(monkeypatch, AsyncMock(return_value=_fake_response(b"real-sounding-audio")))

    audio = await synthesize_speech("A cathedral rises above the hills.")

    assert audio == b"real-sounding-audio"


@pytest.mark.asyncio
async def test_synthesize_speech_uses_default_voice_and_language(monkeypatch):
    mock_call = AsyncMock(return_value=_fake_response())
    _mock_client(monkeypatch, mock_call)

    await synthesize_speech("Some text")

    sent_request = mock_call.call_args.kwargs["request"]
    assert sent_request.voice.language_code == "en-US"
    assert sent_request.voice.name == "en-US-Wavenet-D"
    assert sent_request.input.text == "Some text"


@pytest.mark.asyncio
async def test_synthesize_speech_allows_overriding_voice_and_language(monkeypatch):
    mock_call = AsyncMock(return_value=_fake_response())
    _mock_client(monkeypatch, mock_call)

    await synthesize_speech("Some text", language_code="am-ET", voice_name="am-ET-Custom")

    sent_request = mock_call.call_args.kwargs["request"]
    assert sent_request.voice.language_code == "am-ET"
    assert sent_request.voice.name == "am-ET-Custom"


@pytest.mark.asyncio
async def test_synthesize_speech_retries_on_service_unavailable_then_succeeds(monkeypatch):
    mock_call = AsyncMock(
        side_effect=[
            google_exceptions.ServiceUnavailable("temporarily down"),
            _fake_response(b"recovered audio"),
        ]
    )
    _mock_client(monkeypatch, mock_call)

    audio = await synthesize_speech("Some text")

    assert audio == b"recovered audio"
    assert mock_call.call_count == 2


@pytest.mark.asyncio
async def test_synthesize_speech_raises_after_exhausting_retries(monkeypatch):
    mock_call = AsyncMock(side_effect=google_exceptions.ServiceUnavailable("still down"))
    _mock_client(monkeypatch, mock_call)

    with pytest.raises(TtsClientError):
        await synthesize_speech("Some text")

    assert mock_call.call_count == 3


@pytest.mark.asyncio
async def test_synthesize_speech_does_not_retry_invalid_argument(monkeypatch):
    mock_call = AsyncMock(side_effect=google_exceptions.InvalidArgument("bad voice name"))
    _mock_client(monkeypatch, mock_call)

    with pytest.raises(TtsClientError, match="non-retryable"):
        await synthesize_speech("Some text")

    assert mock_call.call_count == 1
