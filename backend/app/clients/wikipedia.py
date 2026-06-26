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
    response = await _request_with_retries(client, params, log_context=f"geosearch near ({lat}, {lng})")
    return _parse_geosearch_response(response, lat, lng)


async def get_summary(client: httpx.AsyncClient, title: str) -> str:
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "titles": title,
        "format": "json",
    }
    response = await _request_with_retries(client, params, log_context=f"get_summary for '{title}'")
    return _parse_summary_response(response, title)


async def _request_with_retries(
    client: httpx.AsyncClient, params: dict, *, log_context: str
) -> httpx.Response:
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
                "Wikipedia %s network error, attempt %d/%d: %s",
                log_context, attempt, _MAX_ATTEMPTS, exc,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise WikipediaClientError(
                    f"Wikipedia returned non-retryable status "
                    f"{exc.response.status_code} for {log_context}"
                ) from exc
            last_error = exc
            logger.warning(
                "Wikipedia %s got retryable status %d, attempt %d/%d",
                log_context, exc.response.status_code, attempt, _MAX_ATTEMPTS,
            )
        else:
            return response

        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    logger.error("Wikipedia %s failed after %d attempts", log_context, _MAX_ATTEMPTS)
    raise WikipediaClientError(
        f"{log_context} failed after {_MAX_ATTEMPTS} attempts"
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


def _parse_summary_response(response: httpx.Response, title: str) -> str:
    pages = response.json().get("query", {}).get("pages", {})
    if not pages:
        logger.warning("Wikipedia get_summary for '%s' returned no pages", title)
        return ""
    page = next(iter(pages.values()))
    if "missing" in page:
        logger.warning("Wikipedia get_summary: '%s' does not exist", title)
        return ""
    return page.get("extract", "")
