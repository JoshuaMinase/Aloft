from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.dependencies import get_database, get_http_client
from app.services.poi_repository import get_poi
from app.services.story_repository import save_story
from app.services.story_service import InsufficientFactsError, generate_story

router = APIRouter(prefix="/pois", tags=["stories"])


class StoryResponse(BaseModel):
    poi_source_id: str
    language: str
    text_content: str


@router.post("/{source_id}/story", response_model=StoryResponse)
async def create_story(
    source_id: str,
    language: str = "en",
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> StoryResponse:
    poi = await get_poi(db, source_id)
    if poi is None:
        raise HTTPException(
            status_code=404,
            detail=f"No POI found for source_id '{source_id}'. Discover it first via POST /routes/pois.",
        )

    try:
        story = await generate_story(client, source_id, poi.name, language=language)
    except InsufficientFactsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await save_story(db, story)
    return StoryResponse(
        poi_source_id=story.poi_source_id,
        language=story.language,
        text_content=story.text_content,
    )
