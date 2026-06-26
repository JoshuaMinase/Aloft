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
    return request.app.state.http_client


def get_database() -> AsyncIOMotorDatabase:
    return get_db()


@router.post("/pois", response_model=DiscoverPoisResponse)
async def discover_pois(
    body: DiscoverPoisRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoverPoisResponse:
    try:
        pois = await find_pois_along_corridor(
            client,
            departure=(body.departure.lat, body.departure.lng),
            arrival=(body.arrival.lat, body.arrival.lng),
            width_km=body.width_km,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    inserted = await save_pois(db, pois)
    return DiscoverPoisResponse(pois_found=len(pois), pois_newly_inserted=inserted)
