"""
HTTP layer for live flight sessions.

Sessions are stored in Redis (not MongoDB) -- they're short-lived
per-user state that auto-expires after 12 hours. MongoDB is still used
here for route bundle and story lookups, which are permanent shared data.

Position sources (in priority order)
──────────────────────────────────────
1. OpenSky Network (if icao24 or callsign is provided in the request)
   Fetches the live ADS-B position from OpenSky. Useful for the web
   spectator dashboard, or when the mobile client doesn't have GPS.
2. Client-provided lat/lng (always accepted as the fallback)
   The mobile app sends GPS directly. If OpenSky is also requested but
   fails (aircraft not in coverage, rate limit hit), the client lat/lng
   is used instead and a warning is logged.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.clients.opensky import AircraftNotFoundError, OpenSkyClientError, get_aircraft_position
from app.core.config import get_settings
from app.core.dependencies import (
    get_current_user,
    get_database,
    get_http_client,
    get_redis,
    position_update_rate_limit,
)
from app.models.user import User
from app.services.flight_session_repository import (
    create_session,
    get_session,
    record_position_and_narration,
)
from app.services.poi_repository import get_pois_by_source_ids
from app.services.position_tracking_service import (
    DEFAULT_TRIGGER_RADIUS_KM,
    find_next_poi_to_narrate,
)
from app.services.route_bundle_repository import get_route_bundle
from app.services.story_repository import get_story

router = APIRouter(prefix="/sessions", tags=["live session"])
logger = logging.getLogger("aloft.routers.sessions")


class StartSessionRequest(BaseModel):
    route_key: str

    model_config = {"json_schema_extra": {"examples": [{"route_key": "add-dxb-abc123"}]}}


class StartSessionResponse(BaseModel):
    session_id: str
    route_key: str


class PositionUpdateRequest(BaseModel):
    # Client-provided GPS coordinates (always accepted; used as fallback
    # when OpenSky lookup is requested but fails).
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in WGS-84 degrees")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in WGS-84 degrees")
    language: str = "en"
    trigger_radius_km: float = Field(default=DEFAULT_TRIGGER_RADIUS_KM, ge=0.1, le=500.0)

    # Optional: request OpenSky live position instead of (or to override)
    # the client's GPS. Provide one of icao24 or callsign, not both.
    # If OpenSky lookup fails, the client lat/lng above is used as fallback.
    icao24: str | None = None
    callsign: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Mobile app (client GPS)",
                    "value": {
                        "lat": 15.5,
                        "lng": 42.3,
                        "language": "en",
                        "trigger_radius_km": 50,
                    },
                },
                {
                    "summary": "Spectator dashboard (OpenSky)",
                    "value": {
                        "lat": 0.0,
                        "lng": 0.0,
                        "icao24": "4b1806",
                        "language": "en",
                        "trigger_radius_km": 50,
                    },
                },
            ]
        }
    }


class NarrationTrigger(BaseModel):
    source_id: str
    name: str
    text_content: str | None = None


class PositionUpdateResponse(BaseModel):
    triggered: bool
    narration: NarrationTrigger | None = None
    # Reflects the position actually used (OpenSky or client-provided)
    lat_used: float
    lng_used: float
    position_source: str = "client"  # "client" | "opensky"


@router.post(
    "",
    response_model=StartSessionResponse,
    summary="Start a live flight session",
)
async def start_session(
    body: StartSessionRequest,
    _: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis: Redis = Depends(get_redis),
) -> StartSessionResponse:
    """Start a new live flight session for a previously discovered route.

    Returns a `session_id` that you send with each GPS position update.

    Sessions are stored in Redis with a **12-hour TTL** — auto-expires after
    the flight lands, never accumulates in MongoDB.

    404 if `route_key` doesn't match a prior discovery call.
    """
    bundle = await get_route_bundle(db, body.route_key)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=f"No route found for route_key '{body.route_key}'. Discover it first.",
        )

    session = await create_session(redis, body.route_key)
    return StartSessionResponse(session_id=session.session_id, route_key=session.route_key)


@router.post(
    "/{session_id}/position",
    response_model=PositionUpdateResponse,
    summary="Send GPS position and get narration trigger",
    dependencies=[Depends(position_update_rate_limit())],
)
async def update_position(
    session_id: str,
    body: PositionUpdateRequest,
    _: User = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis: Redis = Depends(get_redis),
) -> PositionUpdateResponse:
    """Send the current GPS position and receive a narration trigger if a POI is in range.

    Call this from the mobile app on every GPS fix (every few seconds).

    **Position sources (in priority order):**
    1. **OpenSky Network** — if `icao24` or `callsign` is provided, the live
       ADS-B position is fetched from OpenSky. Useful for the web spectator
       dashboard where the passenger's phone GPS isn't available.
    2. **Client GPS** — the `lat` / `lng` in the request body, used when
       OpenSky is not requested or when OpenSky lookup fails (not in coverage,
       rate limit hit). `position_source` in the response reflects which was used.

    **Narration logic:**
    - Returns `triggered: false` on most calls — nothing new in range.
    - Returns `triggered: true` + narration details when the aircraft enters
      `trigger_radius_km` of an un-narrated POI for the first time.
    - Each POI triggers **at most once** per session.
    - A triggered POI with no pre-generated story returns `text_content: null`.
    """
    session = await get_session(redis, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No session found for '{session_id}'")

    bundle = await get_route_bundle(db, session.route_key)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session's route '{session.route_key}' no longer exists",
        )

    # ---------------------------------------------------------------------------
    # Resolve position: OpenSky first, client GPS as fallback
    # ---------------------------------------------------------------------------
    lat, lng = body.lat, body.lng
    position_source = "client"

    if body.icao24 or body.callsign:
        settings = get_settings()
        try:
            pos = await get_aircraft_position(
                client,
                icao24=body.icao24,
                callsign=body.callsign,
                username=settings.opensky_username,
                password=(
                    settings.opensky_password.get_secret_value()
                    if settings.opensky_password
                    else None
                ),
            )
            lat, lng = pos.latitude, pos.longitude
            position_source = "opensky"
            logger.debug(
                "OpenSky position used for session %s: %.4f, %.4f", session_id, lat, lng
            )
        except AircraftNotFoundError as exc:
            logger.warning(
                "OpenSky: aircraft not found for session %s, falling back to client GPS: %s",
                session_id,
                exc,
            )
        except OpenSkyClientError as exc:
            logger.warning(
                "OpenSky request failed for session %s, falling back to client GPS: %s",
                session_id,
                exc,
            )

    # ---------------------------------------------------------------------------
    # POI proximity check and narration trigger
    # ---------------------------------------------------------------------------
    route_pois = await get_pois_by_source_ids(db, bundle.poi_source_ids)
    already_narrated = set(session.narrated_poi_source_ids)

    next_poi = find_next_poi_to_narrate(
        lat, lng, route_pois, already_narrated, body.trigger_radius_km
    )

    if next_poi is None:
        await record_position_and_narration(redis, session_id, lat, lng, None)
        return PositionUpdateResponse(
            triggered=False,
            lat_used=lat,
            lng_used=lng,
            position_source=position_source,
        )

    story = await get_story(db, next_poi.source_id, body.language)
    await record_position_and_narration(redis, session_id, lat, lng, next_poi.source_id)

    return PositionUpdateResponse(
        triggered=True,
        narration=NarrationTrigger(
            source_id=next_poi.source_id,
            name=next_poi.name,
            text_content=story.text_content if story is not None else None,
        ),
        lat_used=lat,
        lng_used=lng,
        position_source=position_source,
    )
