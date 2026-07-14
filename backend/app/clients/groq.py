from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.api_key_rotation import ApiKeyRotationManager
from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.groq")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0

# Module-level rotation manager cache
_rotation_manager: ApiKeyRotationManager | None = None


def _get_rotation_manager() -> ApiKeyRotationManager:
    """Get or create the API key rotation manager for Groq."""
    global _rotation_manager
    if _rotation_manager is None:
        settings = get_settings()
        # Handle both the property (real Settings) and direct attribute (mocked Settings in tests)
        api_keys = getattr(settings, "groq_api_keys", None)
        if api_keys is None:
            # Fallback for tests that mock Settings without the property
            api_key = settings.groq_api_key
            api_keys = [api_key.get_secret_value()] if api_key else []
        if not api_keys:
            logger.warning("No Groq API keys configured for rotation")
        _rotation_manager = ApiKeyRotationManager("groq", api_keys)
    return _rotation_manager


def reset_rotation_manager_cache() -> None:
    """Clear the cached rotation manager so it's rebuilt from current settings.

    Production never needs this (settings don't change at runtime). It
    exists because the module-level cache above otherwise survives across
    tests in the same pytest process: whichever test calls
    _get_rotation_manager() first "locks in" that test's monkeypatched API
    keys for every test that runs after it. See tests/conftest.py, which
    calls this alongside get_settings.cache_clear() before every test.
    """
    global _rotation_manager
    _rotation_manager = None


def _get_semaphore() -> asyncio.Semaphore:
    """Return a semaphore sized from config.

    Uses a module-level cache keyed on the configured concurrency so the
    same Semaphore is reused across calls (important — creating a new
    Semaphore every call would defeat the purpose entirely).

    Falls back to the default value of 3 if settings are unavailable
    (e.g. in tests that mock the settings object).
    """
    try:
        limit = get_settings().content_generation_max_concurrent
    except (AttributeError, Exception):
        # Settings not available (e.g. mock object in tests) — use safe default.
        limit = 3
    if _get_semaphore._cache_limit != limit:
        _get_semaphore._sem = asyncio.Semaphore(limit)
        _get_semaphore._cache_limit = limit
    return _get_semaphore._sem


_get_semaphore._cache_limit = -1  # type: ignore[attr-defined]
_get_semaphore._sem = asyncio.Semaphore(3)  # type: ignore[attr-defined]


class GroqClientError(Exception):
    pass


async def chat_completion(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.8,
    max_tokens: int = 400,
) -> str:
    from app.core.api_key_rotation import is_key_exhausted, mark_key_exhausted
    
    settings = get_settings()
    rotation_manager = _get_rotation_manager()
    
    # Get API keys from rotation manager or fall back to single key
    api_keys = rotation_manager.api_keys if rotation_manager.api_keys else (
        [settings.groq_api_key.get_secret_value()] if settings.groq_api_key else []
    )
    
    if not api_keys:
        raise GroqClientError("GROQ_API_KEY is not configured")

    payload = {
        "model": model or settings.groq_model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

    # Try each available API key
    for api_key in api_keys:
        # Skip if this key is marked as exhausted (only when using multiple keys)
        if len(api_keys) > 1 and is_key_exhausted("groq", api_key):
            logger.debug("Skipping exhausted Groq API key")
            continue

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        retry_after_override: float | None = None
        should_mark_exhausted = False

        async with _get_semaphore():
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    response = await client.post(
                        GROQ_API_URL, json=payload, headers=headers, timeout=timeout
                    )
                    response.raise_for_status()
                except httpx.TransportError as exc:
                    last_error = exc
                    logger.warning("Groq network error, attempt %d/%d: %s", attempt, _MAX_ATTEMPTS, exc)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                        raise GroqClientError(
                            f"Groq returned non-retryable status {exc.response.status_code}: "
                            f"{exc.response.text[:200]}"
                        ) from exc
                    last_error = exc
                    retry_after_override = _retry_after_seconds(exc.response)
                    # Mark as exhausted if we get 429 (rate limit/quota errors)
                    if exc.response.status_code == 429:
                        should_mark_exhausted = True
                    logger.warning(
                        "Groq got retryable status %d, attempt %d/%d (retry-after=%s)",
                        exc.response.status_code,
                        attempt,
                        _MAX_ATTEMPTS,
                        retry_after_override,
                    )
                else:
                    return _extract_text(response)

                if attempt < _MAX_ATTEMPTS:
                    wait = (
                        retry_after_override
                        if retry_after_override is not None
                        else _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    )
                    await asyncio.sleep(wait)
                    retry_after_override = None

        # If we got here, this key failed all retries - mark it as exhausted if using rotation
        # and we encountered quota/rate limit errors
        if len(api_keys) > 1 and should_mark_exhausted:
            logger.warning("Marking Groq API key as exhausted after quota/rate limit errors")
            mark_key_exhausted("groq", api_key)
        # Continue to next key if using rotation
        if len(api_keys) > 1:
            continue
        # If not using rotation and key failed, raise error  
        break

    raise GroqClientError("chat_completion failed after trying all API keys") from last_error


def _retry_after_seconds(response: httpx.Response) -> float | None:
    val = response.headers.get("retry-after")
    if val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _extract_text(response: httpx.Response) -> str:
    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise GroqClientError(f"Unexpected Groq response shape: {response.text[:200]}") from exc
