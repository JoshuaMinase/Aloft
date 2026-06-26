"""
HTTP layer for POI discovery. Routers only translate between HTTP and the
services underneath -- no business logic lives here, just request/response
shapes and wiring.

Named pois.py, not flights.py: this endpoint takes raw coordinates, not a
flight number. Resolving "ET409" -> actual coordinates is a separate piece
(an OpenSky/AviationStack client) that doesn't exist yet. When it does,
that's a genuinely different router -- this one stays focused on what it
already does honestly.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.db import get_db
from app.services.poi_repository import save_pois
from app.services.poi_service import find_pois_along_corridor

router = APIRouter(prefix="/routes", tags=["pois"])


class Coordinates(BaseModel):
    lat: float
    lng: float


class DiscoverPoisRequest(BaseModel):
    departure: Coordinates
    arrival: Coordinates
    width_km: float = 20.0


class DiscoverPoisResponse(BaseModel):
    pois_found: int
    pois_newly_inserted: int


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Pulled from app.state, set once in main.py's lifespan -- one shared
    connection pool reused across every request, not a new client per call.
    """
    return request.app.state.http_client


def get_database() -> AsyncIOMotorDatabase:
    return get_db()


@router.post("/pois", response_model=DiscoverPoisResponse)
async def discover_pois(
    body: DiscoverPoisRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoverPoisResponse:
    """Discover POIs along a route and persist them.

    Idempotent in effect, not in API style: calling this again for an
    overlapping route won't duplicate anything (poi_repository.save_pois
    upserts by source_id) -- but it's still a POST because it does real
    work (external API calls, writes), not a cache-only read.
    """
    try:
        pois = await find_pois_along_corridor(
            client,
            departure=(body.departure.lat, body.departure.lng),
            arrival=(body.arrival.lat, body.arrival.lng),
            width_km=body.width_km,
        )
    except ValueError as exc:
        # Covers DegenerateRouteError (departure == arrival) and invalid
        # width_km -- both are the caller's mistake, not a server failure.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    inserted = await save_pois(db, pois)
    return DiscoverPoisResponse(pois_found=len(pois), pois_newly_inserted=inserted)
