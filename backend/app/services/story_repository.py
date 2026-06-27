from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.story import Story


async def save_story(db: AsyncIOMotorDatabase, story: Story) -> bool:
    """Upsert a story by (poi_source_id, language). Returns True if newly inserted."""
    result = await db.stories.update_one(
        {"poi_source_id": story.poi_source_id, "language": story.language},
        {"$set": story.to_mongo_dict()},
        upsert=True,
    )
    return result.upserted_id is not None
