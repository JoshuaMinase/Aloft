from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_current_user, get_database, get_http_client
from app.models.user import User
from app.services.download_service import RouteNotFoundError, ZipTooLargeError, build_download_zip

router = APIRouter(prefix="/routes", tags=["offline"])


@router.get(
    "/{route_key}/download",
    summary="Download offline content bundle as a ZIP",
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "ZIP archive with stories, audio, and images",
        },
        404: {"description": "Route key not found"},
    },
)
async def download_route_bundle(
    route_key: str,
    language: str = "en",
    voice_name: str | None = None,
    include_images: bool = True,
    _: User = Depends(get_current_user),
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Response:
    """Download all pre-generated route content as a single ZIP file for offline use.

    The ZIP contains:
    - `manifest.json` — route metadata and POI list
    - `{source_id}/story.txt` — narration text for each POI
    - `{source_id}/audio.mp3` — synthesised audio (if available)
    - `{source_id}/images/` — photos (if `include_images=true`)

    POIs without a story are excluded. POIs with a story but no audio are
    included with text only.

    **Run `POST /routes/{route_key}/content` first** to maximise what's ready —
    this endpoint only packages what has already been generated, it does not
    trigger new generation.
    """
    try:
        zip_bytes = await build_download_zip(
            client,
            db,
            route_key,
            language=language,
            voice_name=voice_name,
            include_images=include_images,
        )
    except RouteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ZipTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=route_{route_key}.zip"},
    )
