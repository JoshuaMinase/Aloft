from __future__ import annotations

import httpx
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.db import get_db
from app.core.redis import get_redis as _get_redis


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_database() -> AsyncIOMotorDatabase:
    return get_db()


def get_redis() -> Redis:
    return _get_redis()
