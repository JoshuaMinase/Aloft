from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from app.core.dependencies import get_current_user, get_database
from app.models.flight_journal import FlightJournalEntry
from app.models.user import User
from app.services.flight_journal_service import (
    get_flight_history, get_user_stats
)

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/stats")
async def my_stats(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    """Returns total flights, distance, countries, places, badges."""
    stats = await get_user_stats(db, current_user.user_id)
    return stats


@router.get("/history")
async def my_flights(
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    """Returns paginated flight history for the journal."""
    entries = await get_flight_history(db, current_user.user_id, limit=limit)
    return {"flights": entries, "count": len(entries)}


@router.get("/share-card/{entry_id}")
async def get_share_card_data(
    entry_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_user),
):
    """Returns structured data for generating a share card on the frontend.
    Frontend renders this as an image. No image generation API needed.
    """
    doc = await db.flight_journal.find_one({
        "entry_id": entry_id,
        "user_id": current_user.user_id,
    })
    if doc is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    doc.pop("_id", None)

    entry = FlightJournalEntry(**doc)
    return {
        "departure": entry.departure_name,
        "arrival": entry.arrival_name,
        "distance_km": round(entry.distance_km),
        "flight_date": entry.flight_date.strftime("%B %d, %Y"),
        "places_narrated": entry.narrated_poi_names[:5],
        "countries": entry.countries_flown_over[:3],
        "tagline": f"Flew over {len(entry.narrated_poi_names)} amazing places",
    }
