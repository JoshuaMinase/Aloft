"""
API Key Rotation Manager

Handles rotation through multiple API keys for external services when quota
limits are reached. Uses Redis to track which keys are exhausted and their
cooldown periods.

Services supported:
- Groq (AI chat completions)
- ElevenLabs (text-to-speech)
- AviationStack (flight data)
- AeroDataBox (flight data)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.core.redis import get_optional_redis

logger = logging.getLogger("aloft.api_key_rotation")

# Redis key prefixes for tracking exhausted API keys
_REDIS_PREFIX = "api_key_exhausted:"
# Cooldown period in seconds before retrying an exhausted key (default: 1 hour)
_DEFAULT_COOLDOWN_SECONDS = 3600


def _get_redis_key(service: str, api_key: str) -> str:
    """Generate a Redis key for tracking an API key's exhausted status."""
    # Hash the API key to avoid storing sensitive data in Redis keys
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return f"{_REDIS_PREFIX}{service}:{key_hash}"


def mark_key_exhausted(
    service: str,
    api_key: str,
    cooldown_seconds: int = _DEFAULT_COOLDOWN_SECONDS,
) -> None:
    """Mark an API key as exhausted with a cooldown period.

    Args:
        service: Service name (e.g., "groq", "elevenlabs", "aviationstack")
        api_key: The API key that hit quota limits
        cooldown_seconds: How long to wait before retrying this key
    """
    redis = get_optional_redis()
    if not redis:
        logger.warning(
            "Redis not available - cannot mark %s API key as exhausted. "
            "Key rotation will not work properly.",
            service,
        )
        return

    redis_key = _get_redis_key(service, api_key)
    # Store metadata about when the key was marked exhausted
    metadata = {
        "marked_at": json.dumps({"timestamp": "manually_marked"}),
        "cooldown": cooldown_seconds,
    }
    redis.setex(redis_key, cooldown_seconds, json.dumps(metadata))
    logger.info(
        "Marked %s API key as exhausted. Cooldown: %d seconds",
        service,
        cooldown_seconds,
    )


def is_key_exhausted(service: str, api_key: str) -> bool:
    """Check if an API key is currently marked as exhausted.

    Args:
        service: Service name (e.g., "groq", "elevenlabs", "aviationstack")
        api_key: The API key to check

    Returns:
        True if the key is exhausted and within cooldown period, False otherwise
    """
    redis = get_optional_redis()
    if not redis:
        # Without Redis, we can't track exhausted keys - assume all are available
        return False

    redis_key = _get_redis_key(service, api_key)
    exists = redis.exists(redis_key)
    if exists:
        logger.debug("API key for %s is currently exhausted", service)
    return bool(exists)


def get_available_key(
    service: str,
    api_keys: list[str],
) -> str | None:
    """Get the first available API key from a list, respecting exhausted status.

    Args:
        service: Service name (e.g., "groq", "elevenlabs", "aviationstack")
        api_keys: List of API keys to choose from

    Returns:
        The first available API key, or None if all keys are exhausted
    """
    if not api_keys:
        logger.error("No API keys provided for service %s", service)
        return None

    for api_key in api_keys:
        if not is_key_exhausted(service, api_key):
            logger.debug("Using available API key for %s", service)
            return api_key
        logger.debug("Skipping exhausted API key for %s", service)

    logger.warning(
        "All %d API keys for %s are exhausted. "
        "Consider adding more keys or waiting for cooldown.",
        len(api_keys),
        service,
    )
    return None


def clear_exhausted_status(service: str, api_key: str) -> None:
    """Manually clear the exhausted status for an API key.

    Useful for testing or when you want to force retry a key before its
    cooldown expires.

    Args:
        service: Service name (e.g., "groq", "elevenlabs", "aviationstack")
        api_key: The API key to clear
    """
    redis = get_optional_redis()
    if not redis:
        return

    redis_key = _get_redis_key(service, api_key)
    redis.delete(redis_key)
    logger.info("Cleared exhausted status for %s API key", service)


def get_exhausted_keys_info(service: str) -> dict[str, Any]:
    """Get information about exhausted keys for a service.

    Args:
        service: Service name (e.g., "groq", "elevenlabs", "aviationstack")

    Returns:
        Dictionary with metadata about exhausted keys (if Redis is available)
    """
    redis = get_optional_redis()
    if not redis:
        return {"error": "Redis not available"}

    # Scan for keys matching the pattern
    pattern = f"{_REDIS_PREFIX}{service}:*"
    keys = []
    try:
        for key in redis.scan_iter(match=pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            ttl = redis.ttl(key_str)
            value = redis.get(key_str)
            metadata = json.loads(value) if value else {}
            keys.append({
                "key_hash": key_str.split(":")[-1],
                "ttl_seconds": ttl,
                "metadata": metadata,
            })
    except Exception as e:
        logger.error("Error scanning for exhausted keys: %s", e)
        return {"error": str(e)}

    return {
        "service": service,
        "exhausted_count": len(keys),
        "keys": keys,
    }


class ApiKeyRotationManager:
    """High-level manager for API key rotation with automatic fallback.

    Usage:
        manager = ApiKeyRotationManager("groq", ["key1", "key2", "key3"])
        api_key = manager.get_key()
        if api_key:
            # Use the key
            try:
                result = make_api_call(api_key)
            except QuotaExceededError:
                manager.mark_current_exhausted()
                # Retry with next key
                api_key = manager.get_key()
    """

    def __init__(self, service: str, api_keys: list[str]):
        """Initialize the rotation manager.

        Args:
            service: Service name (e.g., "groq", "elevenlabs", "aviationstack")
            api_keys: List of API keys to rotate through
        """
        self.service = service
        self.api_keys = api_keys
        self._current_key: str | None = None

    def get_key(self) -> str | None:
        """Get an available API key, automatically rotating if needed.

        Returns:
            An available API key, or None if all keys are exhausted
        """
        # Try to get any available key
        available_key = get_available_key(self.service, self.api_keys)
        if available_key:
            self._current_key = available_key
            return available_key

        # If all keys are exhausted, return None
        self._current_key = None
        return None

    def mark_current_exhausted(
        self,
        cooldown_seconds: int = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        """Mark the current key as exhausted.

        Args:
            cooldown_seconds: How long to wait before retrying this key
        """
        if self._current_key:
            mark_key_exhausted(self.service, self._current_key, cooldown_seconds)
            # Clear current key so next call to get_key() will pick a new one
            self._current_key = None

    def mark_key_exhausted(
        self,
        api_key: str,
        cooldown_seconds: int = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        """Mark a specific API key as exhausted.

        Args:
            api_key: The API key to mark as exhausted
            cooldown_seconds: How long to wait before retrying this key
        """
        mark_key_exhausted(self.service, api_key, cooldown_seconds)
        if self._current_key == api_key:
            self._current_key = None

    def reset(self) -> None:
        """Reset the current key selection.

        Useful when you want to force re-evaluation of available keys.
        """
        self._current_key = None

    @property
    def has_available_keys(self) -> bool:
        """Check if there are any available (non-exhausted) keys."""
        return get_available_key(self.service, self.api_keys) is not None

    @property
    def available_count(self) -> int:
        """Count how many keys are currently available."""
        count = 0
        for key in self.api_keys:
            if not is_key_exhausted(self.service, key):
                count += 1
        return count
