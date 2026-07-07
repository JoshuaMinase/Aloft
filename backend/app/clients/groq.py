from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.groq")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


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
    settings = get_settings()
    if not settings.groq_api_key:
        raise GroqClientError("GROQ_API_KEY is not configured")

    payload = {
        "model": model or settings.groq_model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

    last_error: Exception | None = None
    retry_after_override: float | None = None

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

    raise GroqClientError(f"chat_completion failed after {_MAX_ATTEMPTS} attempts") from last_error


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
