from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from redis.asyncio import Redis

from app.clients.aviationstack import AviationStackClientError, FlightNotFoundError
from app.core.dependencies import (
    flight_lookup_rate_limit,
    get_current_user,
    get_database,
    get_http_client,
    get_redis,
    require_permission,
)
from app.models.role import Permission
from app.models.user import User
from app.services.flight_resolution import resolve_flight_route
from app.services.live_flight_service import LiveFlightError, prepare_live_flight_tracking
from app.services.poi_curator import curate_pois
from app.services.poi_repository import save_pois
from app.services.poi_service import find_pois_along_corridor
from app.services.route_bundle_repository import save_route_bundle

router = APIRouter(prefix="/v1/flights", tags=["discovery", "live tracking"])


class DiscoverPoisByFlightResponse(BaseModel):
    flight_iata: str
    route_key: str
    departure: tuple[float, float]
    arrival: tuple[float, float]
    pois_found: int
    pois_newly_inserted: int


@router.post(
    "/{flight_iata}/pois",
    response_model=DiscoverPoisByFlightResponse,
    summary="Discover POIs for a flight number",
    dependencies=[
        Depends(flight_lookup_rate_limit()),
        Depends(require_permission(Permission.LOOKUP_FLIGHT)),
    ],
)
async def discover_pois_for_flight(
    flight_iata: str,
    width_km: float = Query(
        default=20.0, ge=0.1, le=500.0, description="Corridor width in km (0.1–500)"
    ),
    _: User = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoverPoisByFlightResponse:
    """Look up a flight's route and discover POIs along the corridor.

    Resolves the flight's departure and arrival airports using AviationStack,
    then runs the same POI discovery as `POST /routes/pois`.

    **Rate-limited** (10 requests/hour per IP by default) — AviationStack's
    free tier caps around 100 requests/month total.

    Example: `POST /flights/ET308/pois`
    """
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

    inserted, poi_source_ids = await save_pois(db, pois)

    # Curate POIs to keep only the best ones (quality over quantity)
    curated_pois = curate_pois(pois, departure, arrival)
    curated_source_ids = [f"wikipedia:{p.page_id}" for p in curated_pois]

    bundle = await save_route_bundle(db, departure, arrival, curated_source_ids)

    return DiscoverPoisByFlightResponse(
        flight_iata=flight_iata,
        route_key=bundle.route_key,
        departure=departure,
        arrival=arrival,
        pois_found=len(pois),
        pois_newly_inserted=inserted,
    )


@router.post(
    "/{flight_iata}/live",
    summary="Live flight tracking with real-time stories",
    description=(
        "One-shot endpoint for tracking a currently airborne flight. "
        "Resolves the route, discovers POIs, starts a live session, "
        "fetches the aircraft's live ADS-B position from OpenSky (by callsign), "
        "and returns all nearby stories sorted by distance. "
        "If the aircraft isn't in ADS-B coverage, the route and POIs "
        "are still returned with position_source='unavailable'."
    ),
    dependencies=[
        Depends(flight_lookup_rate_limit()),
        Depends(require_permission(Permission.LOOKUP_FLIGHT)),
    ],
)
async def live_track_flight(
    flight_iata: str,
    language: str = Query("en", description="Story language (e.g. en, ar, fr, de)"),
    width_km: float = Query(default=20.0, ge=0.1, le=500.0, description="Corridor width in km"),
    trigger_radius_km: float = Query(
        default=50.0, ge=0.1, le=500.0, description="Narration trigger radius in km"
    ),
    max_upcoming: int = Query(default=20, ge=0, le=200, description="Max upcoming POIs to return"),
    generate_missing_stories: bool = Query(
        default=True, description="Auto-generate stories for POIs without cached stories"
    ),
    _: User = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Full live-flight experience in a single API call.

    1. Resolves departure/arrival for the flight via AviationStack.
    2. Discovers POIs along the corridor (caches result for reuse).
    3. Creates a live session and returns a `session_id` you can use with
       `POST /v1/sessions/{session_id}/position` for subsequent polling.
    4. Looks up the aircraft's live ADS-B position from OpenSky using its
       callsign. If the aircraft is on the ground or out of coverage,
       the route bundle is still returned with `position_source: "unavailable"`.
    5. Returns all POIs within `trigger_radius_km` of the aircraft with
       cached stories, plus the next `max_upcoming` POIs sorted by distance.
    6. If `generate_missing_stories=true`, generates narration stories
       for any POI without a cached story using the AI story service.

    **Examples**

    - `POST /flights/BA178/live` — full tracking for British Airways BA178
    - `POST /flights/BA178/live?language=ar&trigger_radius_km=30` — Arabic stories within 30 km
    - `POST /flights/LH400/live?width_km=50&max_upcoming=50` — wide corridor with many upcoming POIs
    """
    try:
        result = await prepare_live_flight_tracking(
            client=client,
            db=db,
            redis=redis,
            flight_iata=flight_iata,
            width_km=width_km,
            language=language,
            trigger_radius_km=trigger_radius_km,
            max_upcoming_pois=max_upcoming,
            generate_missing_stories=generate_missing_stories,
        )
    except LiveFlightError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return result.model_dump(mode="json")
