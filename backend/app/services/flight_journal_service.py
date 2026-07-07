from __future__ import annotations
import uuid
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.flight_journal import FlightJournalEntry, UserStats


BADGES = {
    "first_flight":      lambda s: s.total_flights >= 1,
    "five_flights":      lambda s: s.total_flights >= 5,
    "ten_flights":       lambda s: s.total_flights >= 10,
    "world_traveler":    lambda s: s.total_countries >= 10,
    "globe_trotter":     lambda s: s.total_countries >= 25,
    "century_places":    lambda s: s.total_places_narrated >= 100,
    "long_haul":         lambda s: s.total_distance_km >= 10000,
    "around_the_world":  lambda s: s.total_distance_km >= 40075,
}


async def save_flight_journal_entry(
    db: AsyncIOMotorDatabase,
    user_id: str,
    session_data: dict,
) -> FlightJournalEntry:
    """Call this when a flight session ends."""
    entry = FlightJournalEntry(
        entry_id=str(uuid.uuid4()),
        user_id=user_id,
        **session_data,
    )
    await db.flight_journal.insert_one(entry.to_mongo_dict())
    await _update_user_stats(db, user_id, entry)
    return entry


async def get_user_stats(db: AsyncIOMotorDatabase, user_id: str) -> UserStats:
    doc = await db.user_stats.find_one({"user_id": user_id})
    if doc is None:
        return UserStats(user_id=user_id)
    doc.pop("_id", None)
    return UserStats(**doc)


async def get_flight_history(
    db: AsyncIOMotorDatabase, user_id: str, limit: int = 20
) -> list[FlightJournalEntry]:
    cursor = db.flight_journal.find(
        {"user_id": user_id},
        sort=[("flight_date", -1)],
        limit=limit,
    )
    entries = []
    async for doc in cursor:
        doc.pop("_id", None)
        entries.append(FlightJournalEntry(**doc))
    return entries


async def _update_user_stats(
    db: AsyncIOMotorDatabase, user_id: str, entry: FlightJournalEntry
) -> None:
    stats = await get_user_stats(db, user_id)

    stats.total_flights += 1
    stats.total_distance_km += entry.distance_km
    stats.total_places_narrated += len(entry.narrated_poi_names)

    for country in entry.countries_flown_over:
        if country not in stats.all_countries:
            stats.all_countries.append(country)
    stats.total_countries = len(stats.all_countries)

    for poi_name in entry.narrated_poi_names:
        if poi_name not in stats.all_narrated_poi_names:
            stats.all_narrated_poi_names.append(poi_name)

    # Check badges
    for badge_id, condition in BADGES.items():
        if badge_id not in stats.badges_earned and condition(stats):
            stats.badges_earned.append(badge_id)

    await db.user_stats.update_one(
        {"user_id": user_id},
        {"$set": stats.model_dump()},
        upsert=True,
    )
