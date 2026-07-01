"""
Optional Redis connection for rate limiting -- separate from core/redis.py,
which manages the required session-storage connection.

This module uses the same redis_url setting but with different semantics:
Redis is optional here, not required. If REDIS_URL isn't configured or
the server is unreachable, get_redis() returns None and callers fail open
(e.g. the rate limit dependency allows the request rather than blocking
the whole app). This matters because Redis is the one piece of the
zero-cost stack that needs its own signup step (Upstash) -- the app
should still run locally without it during early development.

Currently used for rate limiting (services/rate_limiter.py). The
live-flight-position caching mentioned in the original system design doc
is a natural second use once spectator mode exists.
"""

from __future__ import annotations

import logging

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger("aloft.redis_client")

_client: redis.Redis | None = None
_connection_attempted = False


async def connect_to_redis() -> None:
    """Open the Redis connection if configured. Safe to call even when
    redis_url is None -- becomes a no-op, not an error, since Redis is
    optional infrastructure here, unlike MongoDB.
    """
    global _client, _connection_attempted
    _connection_attempted = True

    settings = get_settings()
    if not settings.redis_url:
        logger.info("REDIS_URL not configured -- rate limiting will fail open")
        return

    _client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await _client.ping()
        logger.info("Connected to Redis (rate-limit client)")
    except Exception:
        logger.exception("Redis configured but unreachable -- rate limiting will fail open")
        _client = None


async def close_redis_connection() -> None:
    global _client, _connection_attempted
    if _client is not None:
        await _client.aclose()
    _client = None
    _connection_attempted = False


def get_redis() -> redis.Redis | None:
    """Returns the Redis client, or None if Redis isn't configured/reachable.

    Deliberately does NOT raise like core.db.get_db() does -- every caller
    of this function must already handle None gracefully (fail open), so
    raising here would just move the same handling one level up for no
    benefit.

    Raises RuntimeError if connect_to_redis() was never called at all
    (i.e. the lifespan hook was never entered). This signals a real wiring
    bug, not a "Redis is down" situation. The rate_limit dependency in
    core/dependencies.py catches this and treats it as fail-open too,
    so tests using bare TestClient(app) work without entering lifespan.
    """
    if not _connection_attempted:
        raise RuntimeError("Redis not initialized. Call connect_to_redis() at app startup first.")
    return _client
