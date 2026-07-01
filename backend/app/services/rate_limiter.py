"""
Per-key request rate limiting, backed by Redis. Protects the genuinely
expensive/quota-limited endpoints -- flight lookups (AviationStack's free
tier caps around 100/month total) and content generation (Groq's free
tier caps around 30/min) -- from being burned through by one retrying
client or one bad actor.

Fixed-window counter, not a sliding window or token bucket: simpler to
reason about and implement correctly with two Redis commands, and "good
enough" for protecting a free-tier quota rather than smoothing genuinely
bursty production traffic. The tradeoff (a client could send 2x the
limit by timing requests across a window boundary) is acceptable here --
the goal is "stop accidental quota exhaustion," not perfect fairness.
"""

from __future__ import annotations

import logging

import redis.asyncio as redis

logger = logging.getLogger("aloft.services.rate_limiter")


class RateLimitExceeded(Exception):
    """Raised when a key has exceeded its allowed requests for the window."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Rate limit exceeded, retry after {retry_after_seconds}s")


async def check_rate_limit(
    redis_client: redis.Redis | None,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """Raise RateLimitExceeded if `key` has made too many requests this window.

    Args:
        redis_client: from core.redis_client.get_redis() -- if None
            (Redis not configured/unreachable), this fails OPEN: the
            request is allowed, a warning is logged, and the app keeps
            working. Rate limiting is a protection layer, not a piece of
            core functionality the app should break without.
        key: e.g. f"ratelimit:flights:{client_ip}" -- callers build this,
            this function just counts against it.
        max_requests: how many requests are allowed per window.
        window_seconds: the fixed window length.

    Raises:
        RateLimitExceeded: if this request would exceed max_requests
            within the current window.
    """
    if redis_client is None:
        logger.warning("Rate limiting skipped (Redis unavailable) for key=%s", key)
        return

    # Atomic counter with expiry using a pipeline:
    # 1. SET key 0 NX EX window_seconds — sets the key with TTL only if it
    #    doesn't already exist (NX). This is atomic at the Redis level and
    #    means the expiry is always set on the very first INCR of a window.
    # 2. INCR key — increment the counter.
    #
    # This is equivalent to the Lua INCR+conditional-EXPIRE approach but uses
    # only native Redis commands that all Redis-compatible clients support,
    # including fakeredis in tests.
    try:
        pipe = redis_client.pipeline()
        await pipe.set(key, 0, nx=True, ex=window_seconds)
        await pipe.incr(key)
        results = await pipe.execute()
        current_count = results[1]  # INCR result
    except redis.RedisError:
        logger.exception("Rate limiter Redis call failed for key=%s -- failing open", key)
        return

    if current_count > max_requests:
        ttl = await redis_client.ttl(key)
        retry_after = ttl if ttl > 0 else window_seconds
        raise RateLimitExceeded(retry_after_seconds=retry_after)
