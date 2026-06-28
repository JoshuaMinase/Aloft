"""
HTTP layer for fetching real photos of a POI. No AI-generated images, no
generic fallback -- if there's nothing real and clear to show, the honest
answer is an empty list, not a fabricated one.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.clients.wikipedia import get_images
from app.core.dependencies import get_database, get_http_client
from app.services.poi_repository import get_poi, save_poi_images

router = APIRouter(prefix="/pois", tags=["images"])


class ImageInfo(BaseModel):
    url: str
    width: int
    height: int
    is_lead_image: bool


class PoiImagesResponse(BaseModel):
    poi_source_id: str
    images: list[ImageInfo]


@router.post("/{source_id}/images", response_model=PoiImagesResponse)
async def fetch_images(
    source_id: str,
    max_images: int = 4,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PoiImagesResponse:
    """Fetch and persist real photos for a previously discovered POI.

    404 if the POI was never discovered. An empty `images` list is a valid
    result -- no real, clear photo exists for this place, not an error.
    """
    poi = await get_poi(db, source_id)
    if poi is None:
        raise HTTPException(
            status_code=404,
            detail=f"No POI found for source_id '{source_id}'. Discover it first via POST /routes/pois.",
        )

    raw_images = await get_images(client, poi.name, max_images=max_images)
    await save_poi_images(db, source_id, [image.url for image in raw_images])

    return PoiImagesResponse(
        poi_source_id=source_id,
        images=[
            ImageInfo(url=img.url, width=img.width, height=img.height, is_lead_image=img.is_lead_image)
            for img in raw_images
        ],
    )
