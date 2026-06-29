from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.services.audio_repository import get_audio
from app.services.poi_repository import get_poi
from app.services.route_bundle_repository import get_route_bundle
from app.services.story_repository import get_story

logger = logging.getLogger("aloft.services.download")


class RouteNotFoundError(Exception):
    pass


async def build_download_zip(
    client: httpx.AsyncClient,
    db: AsyncIOMotorDatabase,
    route_key: str,
    language: str = "en",
    voice_name: str | None = None,
    include_images: bool = True,
) -> bytes:
    """Package already-generated content into a ZIP.

    Raises RouteNotFoundError if route_key doesn't match a known route.
    Run POST /routes/{route_key}/content first to maximise what's ready.
    """
    bundle = await get_route_bundle(db, route_key)
    if bundle is None:
        raise RouteNotFoundError(f"No route found for route_key '{route_key}'")

    resolved_voice = voice_name or get_settings().tts_voice_name
    manifest_entries = []
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for source_id in bundle.poi_source_ids:
            entry = await _package_poi(client, db, zf, source_id, language, resolved_voice, include_images)
            if entry is not None:
                manifest_entries.append(entry)

        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "route_key": route_key,
                    "departure": list(bundle.departure),
                    "arrival": list(bundle.arrival),
                    "language": language,
                    "voice_name": resolved_voice,
                    "poi_count": len(manifest_entries),
                    "pois": manifest_entries,
                },
                indent=2,
            ),
        )

    return buf.getvalue()


async def _package_poi(
    client: httpx.AsyncClient,
    db: AsyncIOMotorDatabase,
    zf: zipfile.ZipFile,
    source_id: str,
    language: str,
    voice_name: str,
    include_images: bool,
) -> dict | None:
    poi = await get_poi(db, source_id)
    if poi is None:
        logger.warning("Skipping %s — POI not found", source_id)
        return None

    story = await get_story(db, source_id, language)
    if story is None:
        logger.warning("Skipping %s — no story yet", source_id)
        return None

    safe_id = source_id.replace(":", "_")
    entry: dict = {
        "source_id": source_id,
        "name": poi.name,
        "location": poi.location,
        "text_content": story.text_content,
        "audio_file": None,
        "image_files": [],
    }

    audio = await get_audio(db, source_id, language, voice_name)
    if audio is not None and Path(audio.file_path).exists():
        filename = f"audio/{safe_id}.mp3"
        zf.writestr(filename, Path(audio.file_path).read_bytes())
        entry["audio_file"] = filename
    else:
        logger.warning("%s has no audio — bundling text only", source_id)

    if include_images and poi.image_refs:
        entry["image_files"] = await _fetch_images(client, zf, poi.image_refs, safe_id)

    return entry


async def _fetch_images(
    client: httpx.AsyncClient, zf: zipfile.ZipFile, urls: list[str], safe_id: str
) -> list[str]:
    filenames = []
    for i, url in enumerate(urls):
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Skipping image %s: %s", url, exc)
            continue
        ext = "jpg" if url.lower().endswith((".jpg", ".jpeg")) else "png"
        filename = f"images/{safe_id}_{i}.{ext}"
        zf.writestr(filename, resp.content)
        filenames.append(filename)
    return filenames
