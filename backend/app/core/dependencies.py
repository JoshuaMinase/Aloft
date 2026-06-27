from __future__ import annotations

import httpx
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.db import get_db


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_database() -> AsyncIOMotorDatabase:
    return get_db()
