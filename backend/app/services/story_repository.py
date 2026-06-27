from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.story import Story


async def get_story(db: AsyncIOMotorDatabase, poi_source_id: str, language: str) -> Story | None:
    doc = await db.stories.find_one({"poi_source_id": poi_source_id, "language": language})
    if doc is None:
        return None
    doc.pop("_id", None)
    return Story(**doc)


async def save_story(db: AsyncIOMotorDatabase, story: Story) -> bool:
    """Upsert a story by (poi_source_id, language). Returns True if newly inserted."""
    result = await db.stories.update_one(
        {"poi_source_id": story.poi_source_id, "language": story.language},
        {"$set": story.to_mongo_dict()},
        upsert=True,
    )
    return result.upserted_id is not None
