from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger("aloft.redis")

_redis: Redis | None = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError(
            "Redis not connected. Call connect_to_redis() at app startup first."
        )
    return _redis


async def connect_to_redis() -> None:
    global _redis
    settings = get_settings()
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # Ping to fail fast if the URL is wrong
    await _redis.ping()
    logger.info("Connected to Redis")


async def close_redis_connection() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None
