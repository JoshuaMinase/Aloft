from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.airport import Airport


async def get_cached_airport(db: AsyncIOMotorDatabase, iata_code: str) -> Airport | None:
    doc = await db.airports.find_one({"iata_code": iata_code})
    if doc is None:
        return None
    doc.pop("_id", None)
    return Airport(**doc)


async def save_airport(db: AsyncIOMotorDatabase, airport: Airport) -> None:
    await db.airports.update_one(
        {"iata_code": airport.iata_code},
        {"$set": airport.to_mongo_dict()},
        upsert=True,
    )
