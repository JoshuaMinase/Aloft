from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import (
    content_generation_rate_limit,
    get_current_user,
    get_database,
    get_http_client,
)
from app.models.user import User
from app.services.content_generation_service import (
    PoiContentResult,
    generate_content_for_route,
)
from app.services.route_bundle_repository import get_route_bundle

router = APIRouter(prefix="/routes", tags=["content"])


class GenerateContentResponse(BaseModel):
    route_key: str
    results: list[PoiContentResult]


@router.post(
    "/{route_key}/content",
    response_model=GenerateContentResponse,
    summary="Batch-generate stories and audio for a route",
    dependencies=[Depends(content_generation_rate_limit())],
)
async def generate_route_content(
    route_key: str,
    language: str = "en",
    _: User = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> GenerateContentResponse:
    """Batch-generate narration stories and ElevenLabs audio for every POI on a route.

    This is the "prepare for flight" step — run it before boarding to pre-cache
    everything so the live session has zero latency per trigger.

    - One Groq (LLaMA 3) call per POI to generate the story text.
    - One ElevenLabs call per POI to synthesise the MP3.
    - Already-generated stories and audio are skipped (idempotent).

    **Rate-limited** (20 requests/hour per IP by default) — a single call can
    fire dozens of Groq and ElevenLabs calls, and both have tight free-tier caps.

    Run `POST /routes/pois` or `POST /flights/{flight_iata}/pois` first to
    get a `route_key`.
    """
    bundle = await get_route_bundle(db, route_key)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No route found for route_key '{route_key}'. Discover it first "
                "via POST /routes/pois or POST /flights/{{flight_iata}}/pois."
            ),
        )

    results = await generate_content_for_route(client, db, bundle.poi_source_ids, language=language)
    return GenerateContentResponse(route_key=route_key, results=results)
