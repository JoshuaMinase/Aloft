"""
HTTP layer for live flight sessions.

Sessions are stored in Redis (not MongoDB) -- they're short-lived
per-user state that auto-expires after 12 hours. MongoDB is still used
here for route bundle and story lookups, which are permanent shared data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from redis.asyncio import Redis

from app.core.dependencies import get_database, get_redis
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

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    route_key: str


class StartSessionResponse(BaseModel):
    session_id: str
    route_key: str


class PositionUpdateRequest(BaseModel):
    lat: float
    lng: float
    language: str = "en"
    trigger_radius_km: float = DEFAULT_TRIGGER_RADIUS_KM


class NarrationTrigger(BaseModel):
    source_id: str
    name: str
    text_content: str | None = None


class PositionUpdateResponse(BaseModel):
    triggered: bool
    narration: NarrationTrigger | None = None


@router.post("", response_model=StartSessionResponse)
async def start_session(
    body: StartSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis: Redis = Depends(get_redis),
) -> StartSessionResponse:
    """Start a new flight session for a previously discovered route.

    404 if route_key doesn't match a prior discovery call.
    Session is stored in Redis with a 12-hour TTL -- auto-expires after
    the flight lands, never accumulates in MongoDB.
    """
    bundle = await get_route_bundle(db, body.route_key)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=f"No route found for route_key '{body.route_key}'. Discover it first.",
        )

    session = await create_session(redis, body.route_key)
    return StartSessionResponse(session_id=session.session_id, route_key=session.route_key)


@router.post("/{session_id}/position", response_model=PositionUpdateResponse)
async def update_position(
    session_id: str,
    body: PositionUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis: Redis = Depends(get_redis),
) -> PositionUpdateResponse:
    """Send a live GPS position; get back the POI to narrate now, if any.

    Returns triggered=false on most calls -- nothing new in range is the
    normal, expected result. Each POI triggers at most once per session.

    A triggered POI with no story generated yet is still marked narrated
    (never silently re-offered) -- text_content comes back null, which is
    the honest signal that content generation hasn't run yet.
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

    route_pois = await get_pois_by_source_ids(db, bundle.poi_source_ids)
    already_narrated = set(session.narrated_poi_source_ids)

    next_poi = find_next_poi_to_narrate(
        body.lat, body.lng, route_pois, already_narrated, body.trigger_radius_km
    )

    if next_poi is None:
        await record_position_and_narration(redis, session_id, body.lat, body.lng, None)
        return PositionUpdateResponse(triggered=False)

    story = await get_story(db, next_poi.source_id, body.language)
    await record_position_and_narration(redis, session_id, body.lat, body.lng, next_poi.source_id)

    return PositionUpdateResponse(
        triggered=True,
        narration=NarrationTrigger(
            source_id=next_poi.source_id,
            name=next_poi.name,
            text_content=story.text_content if story is not None else None,
        ),
    )
