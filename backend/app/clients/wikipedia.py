from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.wikipedia")

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

MAX_RADIUS_M = 10_000
MAX_LIMIT = 500

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5


class RawPoi(BaseModel):
    title: str
    page_id: int
    lat: float
    lng: float
    distance_m: float


class WikipediaClientError(Exception):
    pass


async def geosearch(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    radius_m: int = MAX_RADIUS_M,
    limit: int = 50,
) -> list[RawPoi]:
    if not (0 < radius_m <= MAX_RADIUS_M):
        raise ValueError(f"radius_m must be between 1 and {MAX_RADIUS_M}, got {radius_m}")
    if not (0 < limit <= MAX_LIMIT):
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}, got {limit}")

    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lng}",
        "gsradius": radius_m,
        "gslimit": limit,
        "format": "json",
    }
    headers = {"User-Agent": _user_agent()}
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.get(
                WIKIPEDIA_API_URL, params=params, headers=headers, timeout=timeout
            )
            response.raise_for_status()
        except httpx.TransportError as exc:
            last_error = exc
            logger.warning(
                "Wikipedia geosearch network error near (%s, %s), attempt %d/%d: %s",
                lat, lng, attempt, _MAX_ATTEMPTS, exc,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise WikipediaClientError(
                    f"Wikipedia returned non-retryable status "
                    f"{exc.response.status_code} near ({lat}, {lng})"
                ) from exc
            last_error = exc
            logger.warning(
                "Wikipedia geosearch got retryable status %d near (%s, %s), attempt %d/%d",
                exc.response.status_code, lat, lng, attempt, _MAX_ATTEMPTS,
            )
        else:
            return _parse_geosearch_response(response, lat, lng)

        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    logger.error(
        "Wikipedia geosearch failed after %d attempts near (%s, %s)",
        _MAX_ATTEMPTS, lat, lng,
    )
    raise WikipediaClientError(
        f"geosearch failed after {_MAX_ATTEMPTS} attempts near ({lat}, {lng})"
    ) from last_error


def _user_agent() -> str:
    return f"AloftFlightNarrationApp/0.1 ({get_settings().app_contact_email})"


def _parse_geosearch_response(response: httpx.Response, lat: float, lng: float) -> list[RawPoi]:
    raw_results = response.json().get("query", {}).get("geosearch", [])
    pois: list[RawPoi] = []
    for raw in raw_results:
        try:
            pois.append(
                RawPoi(
                    title=raw["title"],
                    page_id=raw["pageid"],
                    lat=raw["lat"],
                    lng=raw["lon"],
                    distance_m=raw["dist"],
                )
            )
        except KeyError as exc:
            logger.warning(
                "Skipping malformed geosearch result near (%s, %s): missing key %s",
                lat, lng, exc,
            )
    return pois
