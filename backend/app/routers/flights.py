from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.clients.aviationstack import AviationStackClientError, FlightNotFoundError
from app.core.dependencies import get_database, get_http_client
from app.services.flight_resolution import resolve_flight_route
from app.services.poi_repository import save_pois
from app.services.poi_service import find_pois_along_corridor
from app.services.route_bundle_repository import save_route_bundle

router = APIRouter(prefix="/flights", tags=["flights"])


class DiscoverPoisByFlightResponse(BaseModel):
    flight_iata: str
    route_key: str
    departure: tuple[float, float]
    arrival: tuple[float, float]
    pois_found: int
    pois_newly_inserted: int


@router.post("/{flight_iata}/pois", response_model=DiscoverPoisByFlightResponse)
async def discover_pois_for_flight(
    flight_iata: str,
    width_km: float = 20.0,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoverPoisByFlightResponse:
    try:
        departure, arrival = await resolve_flight_route(client, db, flight_iata)
    except FlightNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AviationStackClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        pois = await find_pois_along_corridor(client, departure, arrival, width_km=width_km)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    inserted = await save_pois(db, pois)
    poi_source_ids = [f"wikipedia:{poi.page_id}" for poi in pois]
    bundle = await save_route_bundle(db, departure, arrival, poi_source_ids)

    return DiscoverPoisByFlightResponse(
        flight_iata=flight_iata,
        route_key=bundle.route_key,
        departure=departure,
        arrival=arrival,
        pois_found=len(pois),
        pois_newly_inserted=inserted,
    )
