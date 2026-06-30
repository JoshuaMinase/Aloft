"""
Routes for discovering POIs along a flight corridor.

Two ways to describe the route -- user chooses whichever they have:

  1. Lat/lng directly:
       {"departure": {"lat": 8.98, "lng": 38.79},
        "arrival":   {"lat": 25.25, "lng": 55.36}}

  2. IATA airport codes:
       {"departure_iata": "ADD", "arrival_iata": "DXB"}

  3. Flight number (separate endpoint, uses AviationStack):
       POST /flights/{flight_iata}/pois

IATA lookup order for option 2:
  a) bundled static dataset (~80 major airports, no API call)
  b) MongoDB cache (populated by prior AviationStack lookups)
  If neither has the code, a 422 is returned -- use lat/lng directly
  or look it up via the flights endpoint first.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, model_validator

from app.core.dependencies import get_database, get_http_client
from app.services.airport_repository import get_cached_airport, lookup_static_airport
from app.services.poi_repository import save_pois
from app.services.poi_service import find_pois_along_corridor
from app.services.route_bundle_repository import save_route_bundle

router = APIRouter(prefix="/routes", tags=["pois"])


class Coordinates(BaseModel):
    lat: float
    lng: float


class DiscoverPoisRequest(BaseModel):
    # Option A: lat/lng directly
    departure: Coordinates | None = None
    arrival: Coordinates | None = None

    # Option B: IATA airport codes
    departure_iata: str | None = None
    arrival_iata: str | None = None

    width_km: float = 20.0

    @model_validator(mode="after")
    def check_inputs(self) -> DiscoverPoisRequest:
        has_coords = self.departure is not None and self.arrival is not None
        has_iata = self.departure_iata is not None and self.arrival_iata is not None
        if not has_coords and not has_iata:
            raise ValueError(
                "Provide either departure/arrival coordinates "
                "or departure_iata/arrival_iata airport codes."
            )
        if has_coords and has_iata:
            raise ValueError(
                "Provide coordinates or IATA codes, not both."
            )
        return self


class DiscoverPoisResponse(BaseModel):
    route_key: str
    departure: tuple[float, float]
    arrival: tuple[float, float]
    pois_found: int
    pois_newly_inserted: int


@router.post("/pois", response_model=DiscoverPoisResponse)
async def discover_pois(
    body: DiscoverPoisRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoverPoisResponse:
    """Discover POIs along a flight route.

    Supply either lat/lng coordinates directly, or IATA airport codes.
    IATA codes are resolved against a bundled static dataset (~80 major
    airports) and the local MongoDB cache -- no AviationStack request is
    made here. If an IATA code isn't found in either, a 422 is returned;
    in that case use lat/lng directly or look it up first via
    POST /flights/{flight_iata}/pois.
    """
    if body.departure_iata is not None:
        # IATA path -- resolve codes to coords
        departure = await _resolve_iata(db, body.departure_iata)
        arrival = await _resolve_iata(db, body.arrival_iata)  # type: ignore[arg-type]
    else:
        departure = (body.departure.lat, body.departure.lng)  # type: ignore[union-attr]
        arrival = (body.arrival.lat, body.arrival.lng)        # type: ignore[union-attr]

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
        route_key=bundle.route_key,
        departure=departure,
        arrival=arrival,
        pois_found=len(pois),
        pois_newly_inserted=inserted,
    )


async def _resolve_iata(db: AsyncIOMotorDatabase, iata_code: str) -> tuple[float, float]:
    """Resolve an IATA code to (lat, lng).

    Tries the static dataset first (no I/O), then the DB cache.
    Raises HTTP 422 if neither has the code.
    """
    iata_upper = iata_code.upper()

    coords = lookup_static_airport(iata_upper)
    if coords is not None:
        return coords

    cached = await get_cached_airport(db, iata_upper)
    if cached is not None:
        return (cached.lat, cached.lng)

    raise HTTPException(
        status_code=422,
        detail=(
            f"Airport '{iata_upper}' not found in the static dataset or local cache. "
            f"Use lat/lng coordinates directly, or discover it first via "
            f"POST /flights/{{flight_iata}}/pois to populate the cache."
        ),
    )
