"""
Test API key rotation functionality.

This test verifies that the API key rotation system works correctly
when services return quota/rate limit errors.
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.clients.groq import GroqClientError, chat_completion
from app.clients.tts import TtsClientError, synthesize_speech
from app.core.api_key_rotation import (
    ApiKeyRotationManager,
    clear_exhausted_status,
    get_available_key,
    is_key_exhausted,
    mark_key_exhausted,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("app.core.api_key_rotation.get_optional_redis") as mock:
        redis_mock = Mock()
        redis_mock.exists = Mock(return_value=False)
        redis_mock.setex = Mock()
        redis_mock.ttl = Mock(return_value=3600)
        redis_mock.get = Mock(return_value=None)
        redis_mock.delete = Mock()
        redis_mock.scan_iter = Mock(return_value=[])
        mock.return_value = redis_mock
        yield redis_mock


class TestApiKeyRotationManager:
    """Test the ApiKeyRotationManager class."""

    def test_rotation_manager_initialization(self):
        """Test that rotation manager initializes correctly."""
        manager = ApiKeyRotationManager("test_service", ["key1", "key2", "key3"])
        assert manager.service == "test_service"
        assert manager.api_keys == ["key1", "key2", "key3"]
        assert manager._current_key is None

    def test_get_key_returns_first_available(self, mock_redis):
        """Test that get_key returns the first available key."""
        manager = ApiKeyRotationManager("test_service", ["key1", "key2"])
        key = manager.get_key()
        assert key == "key1"

    def test_get_key_skips_exhausted(self, mock_redis):
        """Test that get_key skips exhausted keys."""
        # The actual Redis key includes a hash, so we need to mock accordingly
        mock_redis.exists = Mock(return_value=True)  # First key is exhausted
        manager = ApiKeyRotationManager("test_service", ["key1", "key2"])
        
        # Mock is_key_exhausted to return True for key1, False for key2
        with patch("app.core.api_key_rotation.is_key_exhausted") as mock_exhausted:
            mock_exhausted.side_effect = lambda service, key: key == "key1"
            key = manager.get_key()
            assert key == "key2"

    def test_get_key_returns_none_when_all_exhausted(self, mock_redis):
        """Test that get_key returns None when all keys are exhausted."""
        mock_redis.exists = Mock(return_value=True)
        manager = ApiKeyRotationManager("test_service", ["key1", "key2"])
        key = manager.get_key()
        assert key is None

    def test_mark_current_exhausted(self, mock_redis):
        """Test marking the current key as exhausted."""
        manager = ApiKeyRotationManager("test_service", ["key1", "key2"])
        manager.get_key()  # Set current key to key1
        manager.mark_current_exhausted()
        mock_redis.setex.assert_called_once()
        assert manager._current_key is None

    def test_has_available_keys(self, mock_redis):
        """Test checking if available keys exist."""
        manager = ApiKeyRotationManager("test_service", ["key1", "key2"])
        assert manager.has_available_keys is True

        mock_redis.exists = Mock(return_value=True)
        assert manager.has_available_keys is False

    def test_available_count(self, mock_redis):
        """Test counting available keys."""
        manager = ApiKeyRotationManager("test_service", ["key1", "key2", "key3"])
        assert manager.available_count == 3

        # Mock is_key_exhausted to return True for key1 and key2, False for key3
        with patch("app.core.api_key_rotation.is_key_exhausted") as mock_exhausted:
            mock_exhausted.side_effect = lambda service, key: key in ["key1", "key2"]
            assert manager.available_count == 1


class TestApiKeyRotationFunctions:
    """Test the standalone API key rotation functions."""

    def test_mark_key_exhausted(self, mock_redis):
        """Test marking a key as exhausted."""
        mark_key_exhausted("test_service", "test_key")
        mock_redis.setex.assert_called_once()

    def test_is_key_exhausted(self, mock_redis):
        """Test checking if a key is exhausted."""
        mock_redis.exists = Mock(return_value=True)
        assert is_key_exhausted("test_service", "test_key") is True

        mock_redis.exists = Mock(return_value=False)
        assert is_key_exhausted("test_service", "test_key") is False

    def test_get_available_key(self, mock_redis):
        """Test getting an available key from a list."""
        keys = ["key1", "key2", "key3"]
        key = get_available_key("test_service", keys)
        assert key == "key1"

        # Mock is_key_exhausted to return True for key1, False for others
        with patch("app.core.api_key_rotation.is_key_exhausted") as mock_exhausted:
            mock_exhausted.side_effect = lambda service, key: key == "key1"
            key = get_available_key("test_service", keys)
            assert key == "key2"

    def test_clear_exhausted_status(self, mock_redis):
        """Test clearing exhausted status."""
        clear_exhausted_status("test_service", "test_key")
        mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
class TestGroqClientRotation:
    """Test Groq client with API key rotation."""

    async def test_groq_rotation_on_429_error(self):
        """Test that Groq client rotates to next key on 429 error."""
        with patch("app.clients.groq._get_rotation_manager") as mock_manager:
            mock_manager.return_value = ApiKeyRotationManager("groq", ["key1", "key2"])
            
            mock_settings = Mock()
            mock_settings.groq_api_keys = ["key1", "key2"]
            mock_settings.groq_model = "test-model"
            mock_settings.content_generation_max_concurrent = 3
            
            with patch("app.clients.groq.get_settings", return_value=mock_settings):
                mock_client = AsyncMock()
                # First key fails with 429, second succeeds
                mock_client.post.side_effect = [
                    httpx.HTTPStatusError(
                        "Rate limit exceeded",
                        request=Mock(),
                        response=Mock(status_code=429, headers=Mock(get=Mock(return_value=None)))
                    ),
                    Mock(
                        raise_for_status=Mock(),
                        json=Mock(return_value={"choices": [{"message": {"content": "test response"}}]})
                    )
                ]
                
                with patch("app.core.api_key_rotation.is_key_exhausted", return_value=False), \
                     patch("app.core.api_key_rotation.mark_key_exhausted"):
                    result = await chat_completion(mock_client, [{"role": "user", "content": "test"}])
                    assert result == "test response"

    async def test_groq_fails_when_all_keys_exhausted(self):
        """Test that Groq client fails when all keys are exhausted."""
        with patch("app.clients.groq._get_rotation_manager") as mock_manager:
            mock_manager.return_value = ApiKeyRotationManager("groq", ["key1", "key2"])
            
            mock_settings = Mock()
            mock_settings.groq_api_keys = ["key1", "key2"]
            mock_settings.groq_model = "test-model"
            mock_settings.content_generation_max_concurrent = 3
            
            with patch("app.clients.groq.get_settings", return_value=mock_settings):
                mock_client = AsyncMock()
                # Both keys fail with 429
                mock_client.post.side_effect = httpx.HTTPStatusError(
                    "Rate limit exceeded",
                    request=Mock(),
                    response=Mock(status_code=429, headers=Mock(get=Mock(return_value=None)))
                )
                
                with patch("app.core.api_key_rotation.is_key_exhausted", return_value=False), \
                     patch("app.core.api_key_rotation.mark_key_exhausted"), \
                     pytest.raises(GroqClientError):
                    await chat_completion(mock_client, [{"role": "user", "content": "test"}])


@pytest.mark.asyncio
class TestTtsClientRotation:
    """Test TTS client with API key rotation."""

    async def test_tts_rotation_on_429_error(self):
        """Test that TTS client rotates to next key on 429 error."""
        with patch("app.clients.tts._get_rotation_manager") as mock_manager:
            mock_manager.return_value = ApiKeyRotationManager("elevenlabs", ["key1", "key2"])
            
            with patch("app.clients.tts.get_settings") as mock_settings:
                mock_settings.return_value.elevenlabs_api_keys = ["key1", "key2"]
                mock_settings.return_value.elevenlabs_voice_id = "test-voice"
                
                mock_client = AsyncMock()
                # First key fails with 429, second succeeds
                mock_client.post.side_effect = [
                    Mock(status_code=429, text="Rate limit exceeded"),
                    Mock(status_code=200, content=b"audio data")
                ]
                
                with patch("app.core.api_key_rotation.is_key_exhausted", return_value=False), \
                     patch("app.core.api_key_rotation.mark_key_exhausted"):
                    result = await synthesize_speech("test text", http_client=mock_client)
                    assert result == b"audio data"

    async def test_tts_fails_when_all_keys_exhausted(self):
        """Test that TTS client fails when all keys are exhausted."""
        with patch("app.clients.tts._get_rotation_manager") as mock_manager:
            mock_manager.return_value = ApiKeyRotationManager("elevenlabs", ["key1", "key2"])
            
            with patch("app.clients.tts.get_settings") as mock_settings:
                mock_settings.return_value.elevenlabs_api_keys = ["key1", "key2"]
                mock_settings.return_value.elevenlabs_voice_id = "test-voice"
                
                mock_client = AsyncMock()
                # Both keys fail with 429
                mock_client.post.return_value = Mock(status_code=429, text="Rate limit exceeded")
                
                with patch("app.core.api_key_rotation.is_key_exhausted", return_value=False), \
                     patch("app.core.api_key_rotation.mark_key_exhausted"), \
                     pytest.raises(TtsClientError):
                    await synthesize_speech("test text", http_client=mock_client)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
