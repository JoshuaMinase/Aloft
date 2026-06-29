from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_database, get_http_client
from app.services.download_service import RouteNotFoundError, build_download_zip

router = APIRouter(prefix="/routes", tags=["download"])


@router.get("/{route_key}/download")
async def download_route_bundle(
    route_key: str,
    language: str = "en",
    voice_name: str | None = None,
    include_images: bool = True,
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Response:
    """Download pre-generated route content as a ZIP.

    404 if route_key is unknown. POIs without a story are excluded; POIs
    with a story but no audio are included with text only. Run POST
    /routes/{route_key}/content first to maximise what's ready.
    """
    try:
        zip_bytes = await build_download_zip(
            client, db, route_key,
            language=language, voice_name=voice_name, include_images=include_images,
        )
    except RouteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=route_{route_key}.zip"},
    )
