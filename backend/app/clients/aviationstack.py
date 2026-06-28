from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.aviationstack")

AVIATIONSTACK_BASE_URL = "https://api.aviationstack.com/v1"

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5
_NON_RETRYABLE_429_CODES = {"usage_limit_reached"}


class FlightInfo(BaseModel):
    flight_iata: str
    departure_iata: str
    arrival_iata: str
    flight_status: str


class AirportInfo(BaseModel):
    iata_code: str
    name: str
    lat: float
    lng: float


class AviationStackClientError(Exception):
    pass


class FlightNotFoundError(AviationStackClientError):
    pass


async def get_flight(client: httpx.AsyncClient, flight_iata: str) -> FlightInfo:
    results = await _request(client, "flights", {"flight_iata": flight_iata})
    if not results:
        raise FlightNotFoundError(f"No flight found for '{flight_iata}'")

    flight = results[0]
    departure_iata = (flight.get("departure") or {}).get("iata")
    arrival_iata = (flight.get("arrival") or {}).get("iata")
    if not departure_iata or not arrival_iata:
        raise AviationStackClientError(
            f"Flight '{flight_iata}' is missing a departure or arrival IATA code"
        )

    return FlightInfo(
        flight_iata=flight_iata,
        departure_iata=departure_iata,
        arrival_iata=arrival_iata,
        flight_status=flight.get("flight_status") or "unknown",
    )


async def get_airport(client: httpx.AsyncClient, iata_code: str) -> AirportInfo:
    results = await _request(client, "airports", {"iata_code": iata_code})
    if not results:
        raise AviationStackClientError(f"No airport found for IATA code '{iata_code}'")

    airport = results[0]
    lat, lng = airport.get("latitude"), airport.get("longitude")
    if lat is None or lng is None:
        raise AviationStackClientError(f"Airport '{iata_code}' is missing coordinates")

    return AirportInfo(
        iata_code=iata_code,
        name=airport.get("airport_name") or iata_code,
        lat=float(lat),
        lng=float(lng),
    )


async def _request(client: httpx.AsyncClient, endpoint: str, params: dict) -> list[dict]:
    settings = get_settings()
    url = f"{AVIATIONSTACK_BASE_URL}/{endpoint}"
    full_params = {"access_key": settings.aviationstack_api_key, **params}
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.get(url, params=full_params, timeout=timeout)
            if response.status_code == 429 and _is_quota_exhausted(response):
                raise AviationStackClientError(
                    "AviationStack monthly request quota is exhausted -- "
                    "retrying won't help until the next billing cycle."
                )
            response.raise_for_status()
        except httpx.TransportError as exc:
            last_error = exc
            logger.warning("AviationStack %s network error, attempt %d/%d: %s", endpoint, attempt, _MAX_ATTEMPTS, exc)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise AviationStackClientError(
                    f"AviationStack returned non-retryable status {exc.response.status_code} for {endpoint}"
                ) from exc
            last_error = exc
            logger.warning("AviationStack %s got retryable status %d, attempt %d/%d", endpoint, exc.response.status_code, attempt, _MAX_ATTEMPTS)
        else:
            return response.json().get("data", [])

        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    raise AviationStackClientError(
        f"{endpoint} request failed after {_MAX_ATTEMPTS} attempts"
    ) from last_error


def _is_quota_exhausted(response: httpx.Response) -> bool:
    try:
        error_code = response.json().get("error", {}).get("code")
    except ValueError:
        return False
    return error_code in _NON_RETRYABLE_429_CODES
