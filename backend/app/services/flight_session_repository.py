from __future__ import annotations

import uuid
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.flight_session import FlightSession


async def create_session(db: AsyncIOMotorDatabase, route_key: str) -> FlightSession:
    session = FlightSession(session_id=str(uuid.uuid4()), route_key=route_key)
    await db.flight_sessions.insert_one(session.to_mongo_dict())
    return session


async def get_session(db: AsyncIOMotorDatabase, session_id: str) -> FlightSession | None:
    doc = await db.flight_sessions.find_one({"session_id": session_id})
    if doc is None:
        return None
    doc.pop("_id", None)
    return FlightSession(**doc)


async def record_position_and_narration(
    db: AsyncIOMotorDatabase,
    session_id: str,
    lat: float,
    lng: float,
    newly_narrated_source_id: str | None,
) -> None:
    """Update a session's last known position and, if a POI was triggered
    this update, add it to the narrated list.

    $addToSet makes recording the same POI twice idempotent -- a retried
    request won't create duplicate entries.
    """
    update: dict = {
        "$set": {"last_position": [lat, lng], "last_updated_at": datetime.now(UTC)}
    }
    if newly_narrated_source_id is not None:
        update["$addToSet"] = {"narrated_poi_source_ids": newly_narrated_source_id}

    await db.flight_sessions.update_one({"session_id": session_id}, update)
