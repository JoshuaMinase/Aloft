from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import close_mongo_connection, connect_to_mongo
from app.routers import audio, content, flights, images, pois, stories

logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("aloft.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await connect_to_mongo()
    app.state.http_client = httpx.AsyncClient()
    logger.info("Aloft backend started")
    yield
    await app.state.http_client.aclose()
    await close_mongo_connection()
    logger.info("Aloft backend shut down")


app = FastAPI(title="Aloft", lifespan=lifespan)
app.include_router(pois.router)
app.include_router(stories.router)
app.include_router(audio.router)
app.include_router(flights.router)
app.include_router(images.router)
app.include_router(content.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
