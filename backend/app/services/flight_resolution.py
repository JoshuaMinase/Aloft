from __future__ import annotations

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.aviationstack import get_airport, get_flight
from app.models.airport import Airport
from app.services.airport_repository import get_cached_airport, save_airport


async def resolve_flight_route(
    client: httpx.AsyncClient, db: AsyncIOMotorDatabase, flight_iata: str
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Resolve a flight number to (departure_coords, arrival_coords).

    Returns:
        ((dep_lat, dep_lng), (arr_lat, arr_lng))
    """
    flight = await get_flight(client, flight_iata)
    departure = await _resolve_airport_coords(client, db, flight.departure_iata)
    arrival = await _resolve_airport_coords(client, db, flight.arrival_iata)
    return departure, arrival


async def _resolve_airport_coords(
    client: httpx.AsyncClient, db: AsyncIOMotorDatabase, iata_code: str
) -> tuple[float, float]:
    cached = await get_cached_airport(db, iata_code)
    if cached is not None:
        return (cached.lat, cached.lng)

    fetched = await get_airport(client, iata_code)
    await save_airport(
        db,
        Airport(iata_code=fetched.iata_code, name=fetched.name, lat=fetched.lat, lng=fetched.lng),
    )
    return (fetched.lat, fetched.lng)
