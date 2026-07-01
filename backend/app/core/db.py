from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

logger = logging.getLogger("aloft.db")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_to_mongo() at app startup first.")
    return _db


async def connect_to_mongo() -> None:
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.mongodb_db_name]
    await ensure_indexes(_db)
    logger.info("Connected to MongoDB database '%s'", settings.mongodb_db_name)


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.pois.create_index([("location", "2dsphere")])
    await db.pois.create_index("source_id", unique=True, sparse=True)
    await db.stories.create_index([("poi_source_id", 1), ("language", 1)], unique=True)
    await db.airports.create_index("iata_code", unique=True)
    await db.route_bundles.create_index("route_key", unique=True)
    # Users: unique email lookup for login; case-insensitive via lowercase storage.
    await db.users.create_index("email", unique=True)
    # Audio assets: queried by (poi_source_id, language, voice_name) on every audio
    # request and every content generation step. Without this index every lookup is
    # a full collection scan.
    await db.audio_assets.create_index(
        [("poi_source_id", 1), ("language", 1), ("voice_name", 1)],
        unique=True,
    )
    # Note: flight_sessions are in Redis (with TTL), not MongoDB.
