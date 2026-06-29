from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_database, get_http_client
from app.services.poi_repository import save_pois
from app.services.poi_service import find_pois_along_corridor
from app.services.route_bundle_repository import save_route_bundle

router = APIRouter(prefix="/routes", tags=["pois"])


class Coordinates(BaseModel):
    lat: float
    lng: float


class DiscoverPoisRequest(BaseModel):
    departure: Coordinates
    arrival: Coordinates
    width_km: float = 20.0


class DiscoverPoisResponse(BaseModel):
    route_key: str
    pois_found: int
    pois_newly_inserted: int


@router.post("/pois", response_model=DiscoverPoisResponse)
async def discover_pois(
    body: DiscoverPoisRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoverPoisResponse:
    departure = (body.departure.lat, body.departure.lng)
    arrival = (body.arrival.lat, body.arrival.lng)

    try:
        pois = await find_pois_along_corridor(
            client, departure=departure, arrival=arrival, width_km=body.width_km
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    inserted = await save_pois(db, pois)
    poi_source_ids = [f"wikipedia:{poi.page_id}" for poi in pois]
    bundle = await save_route_bundle(db, departure, arrival, poi_source_ids)

    return DiscoverPoisResponse(
        route_key=bundle.route_key, pois_found=len(pois), pois_newly_inserted=inserted
    )
