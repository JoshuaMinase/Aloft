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
    logger.info("Connecting to MongoDB at %s", settings.mongodb_uri)
    try:
        kwargs = {
            "serverSelectionTimeoutMS": 30000,
            "connectTimeoutMS": 30000,
            "retryWrites": True,
            "w": "majority",
        }
        _client = AsyncIOMotorClient(settings.mongodb_uri, **kwargs)
        _db = _client[settings.mongodb_db_name]
        await _db.command("ping")
        logger.info("MongoDB ping OK")
    except Exception as exc:
        logger.error("MongoDB connection failed: %s", exc)
        raise

    try:
        await ensure_indexes(_db)
    except Exception as exc:
        logger.error("MongoDB index creation failed: %s", exc)
        raise

    logger.info("Connected to MongoDB database '%s'", settings.mongodb_db_name)


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    index_defs = [
        (db.pois, [("location", "2dsphere")], "pois_location_2dsphere"),
        (db.pois, ["source_id"], "pois_source_id_unique", {"unique": True, "sparse": True}),
        (db.stories, [("poi_source_id", 1), ("language", 1)], "stories_poi_lang_unique", {"unique": True}),
        (db.airports, ["iata_code"], "airports_iata_unique", {"unique": True}),
        (db.route_bundles, ["route_key"], "route_bundles_route_key_unique", {"unique": True}),
        (db.users, ["email"], "users_email_unique", {"unique": True}),
        (db.audio_assets, [("poi_source_id", 1), ("language", 1), ("voice_name", 1)], "audio_assets_poi_lang_voice_unique", {"unique": True}),
    ]
    for collection, keys, name, *rest in index_defs:
        try:
            kwargs = rest[0] if rest else {}
            await collection.create_index(keys, name=name, **kwargs)
            logger.debug("Created index %s on %s", name, collection.name)
        except Exception as exc:
            logger.warning("Index %s creation failed: %s", name, exc)
