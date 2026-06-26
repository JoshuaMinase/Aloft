"""
Persists discovered POIs to MongoDB. Upserts by source_id so re-running
discovery on overlapping routes never creates duplicate documents -- this
is what makes the "cache once per POI, reuse forever across every flight
that crosses the same geography" architecture actually work, not just a
plan on paper.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.wikipedia import RawPoi
from app.models.poi import Poi


async def save_pois(db: AsyncIOMotorDatabase, pois: list[RawPoi]) -> int:
    """Upsert each discovered POI by source_id.

    Args:
        db: an active database handle (real Motor in production, or a
            mongomock database in tests -- this function doesn't care).
        pois: raw results from poi_service.find_pois_along_corridor().

    Returns:
        Count of POIs that were newly inserted. A POI that already
        existed (same source_id, found again on an overlapping route)
        gets its fields refreshed but doesn't count as new.
    """
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
