from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.wikipedia import RawPoi
from app.models.poi import Poi


async def save_pois(db: AsyncIOMotorDatabase, pois: list[RawPoi]) -> int:
    """Upsert each POI by source_id. Returns count of newly inserted documents."""
    inserted_count = 0
    for raw in pois:
        poi = Poi.from_wikipedia_poi(raw)
        result = await db.pois.update_one(
            {"source_id": poi.source_id},
            {"$set": poi.to_mongo_dict()},
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted_count += 1
    return inserted_count
