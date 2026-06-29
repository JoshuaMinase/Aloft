from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_database, get_http_client
from app.services.content_generation_service import (
    PoiContentResult,
    generate_content_for_route,
)
from app.services.route_bundle_repository import get_route_bundle

router = APIRouter(prefix="/routes", tags=["content"])


class GenerateContentResponse(BaseModel):
    route_key: str
    results: list[PoiContentResult]


@router.post("/{route_key}/content", response_model=GenerateContentResponse)
async def generate_route_content(
    route_key: str,
    language: str = "en",
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> GenerateContentResponse:
    bundle = await get_route_bundle(db, route_key)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No route found for route_key '{route_key}'. Discover it first "
                "via POST /routes/pois or POST /flights/{{flight_iata}}/pois."
            ),
        )

    results = await generate_content_for_route(
        client, db, bundle.poi_source_ids, language=language
    )
    return GenerateContentResponse(route_key=route_key, results=results)
