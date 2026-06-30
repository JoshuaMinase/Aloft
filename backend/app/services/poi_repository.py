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


async def get_poi(db: AsyncIOMotorDatabase, source_id: str) -> Poi | None:
    doc = await db.pois.find_one({"source_id": source_id})
    if doc is None:
        return None
    doc.pop("_id", None)
    return Poi(**doc)



async def save_poi_images(db: AsyncIOMotorDatabase, source_id: str, image_urls: list[str]) -> None:
    """Update a POI's image_refs after fetching real photos for it.

    image_urls may be an empty list -- that's the honest "no real images
    exist" outcome, not an error, and gets stored as such rather than left
    unset and ambiguous with "never checked."
    """
    await db.pois.update_one({"source_id": source_id}, {"$set": {"image_refs": image_urls}})


async def get_pois_by_source_ids(db: AsyncIOMotorDatabase, source_ids: list[str]) -> list[Poi]:
    """Fetch many POIs in one query -- $in avoids N round trips for N source_ids."""
    cursor = db.pois.find({"source_id": {"$in": source_ids}})
    pois = []
    async for doc in cursor:
        doc.pop("_id", None)
        pois.append(Poi(**doc))
    return pois
