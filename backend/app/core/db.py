"""
MongoDB connection, kept in one place on purpose.

The client is created lazily -- via connect_to_mongo(), called once from
main.py's startup -- never at import time. That's what lets every other
module import app.* freely without needing a live database, and what lets
tests pass in a mongomock database instead of a real one.
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

logger = logging.getLogger("aloft.db")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    """Returns the active database handle. Raises if connect_to_mongo() hasn't run."""
    if _db is None:
        raise RuntimeError(
            "Database not connected. Call connect_to_mongo() at app startup first."
        )
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
    """Indexes this app depends on for correctness or performance.

    Public (not prefixed with _) because tests call this directly against
    a mongomock database -- the index behavior itself is part of what
    needs verifying, not just an implementation detail.
    """
    await db.pois.create_index([("location", "2dsphere")])
    # unique + sparse: source_id is what save_pois() upserts against to
    # avoid storing the same Wikipedia page twice.
    await db.pois.create_index("source_id", unique=True, sparse=True)
