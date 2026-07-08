"""
AeroDataBox via RapidAPI -- flight number to route resolution.
Better than AviationStack for Aloft because it returns airport
coordinates in the same response (no second /airports call needed).

Free tier: 500 requests/month via RapidAPI. No credit card required.
Sign up at: rapidapi.com/aedbx-aedbx/api/aerodatabox
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger("aloft.clients.aerodatabox")

AERODATABOX_BASE_URL = "https://aerodatabox.p.rapidapi.com"

# 429 from RapidAPI means monthly quota exhausted -- not a transient rate limit.
# Retrying will just waste quota. Treat it as a hard, non-retryable failure.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_MAX_ATTEMPTS = 3


class AeroDataBoxFlightInfo(BaseModel):
    flight_iata: str
    departure_iata: str
    arrival_iata: str
    departure_lat: float
    departure_lng: float
    arrival_lat: float
    arrival_lng: float
    status: str


class AeroDataBoxClientError(Exception):
    pass


class FlightNotFoundError(AeroDataBoxClientError):
    pass


async def get_flight(
    client: httpx.AsyncClient,
    flight_iata: str,
) -> AeroDataBoxFlightInfo:
    """Resolve a flight number to route + airport coordinates.
    One call returns everything -- no second airport lookup needed.
    """
    settings = get_settings()
    if not settings.aerodatabox_api_key:
        raise AeroDataBoxClientError("AERODATABOX_API_KEY not configured")

    headers = {
        "x-rapidapi-host": "aerodatabox.p.rapidapi.com",
        "x-rapidapi-key": settings.aerodatabox_api_key,
    }

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.get(
                f"{AERODATABOX_BASE_URL}/flights/number/{flight_iata}",
                headers=headers,
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise FlightNotFoundError(f"Flight '{flight_iata}' not found") from exc
            if exc.response.status_code == 429:
                raise AeroDataBoxClientError(
                    "AeroDataBox monthly quota exhausted -- retrying won't help until next billing cycle"
                ) from exc
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise AeroDataBoxClientError(
                    f"Non-retryable error: {exc.response.status_code}"
                ) from exc
            last_error = exc
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            continue
        except httpx.TransportError as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            continue
        else:
            return _parse_response(response, flight_iata)

    raise AeroDataBoxClientError(f"Failed after {_MAX_ATTEMPTS} attempts") from last_error


def _parse_response(response: httpx.Response, flight_iata: str) -> AeroDataBoxFlightInfo:
    data = response.json()

    # AeroDataBox returns a list; take the first active/scheduled result
    flights = data if isinstance(data, list) else [data]
    if not flights:
        raise FlightNotFoundError(f"No data for flight '{flight_iata}'")

    flight = flights[0]
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    dep_airport = dep.get("airport", {})
    arr_airport = arr.get("airport", {})

    dep_iata = dep_airport.get("iata")
    arr_iata = arr_airport.get("iata")
    dep_lat = dep_airport.get("location", {}).get("lat")
    dep_lng = dep_airport.get("location", {}).get("lon")
    arr_lat = arr_airport.get("location", {}).get("lat")
    arr_lng = arr_airport.get("location", {}).get("lon")

    if not all([dep_iata, arr_iata, dep_lat, dep_lng, arr_lat, arr_lng]):
        raise AeroDataBoxClientError(
            f"Incomplete airport data for '{flight_iata}': "
            f"dep={dep_iata}({dep_lat},{dep_lng}) arr={arr_iata}({arr_lat},{arr_lng})"
        )

    return AeroDataBoxFlightInfo(
        flight_iata=flight_iata,
        departure_iata=dep_iata,
        arrival_iata=arr_iata,
        departure_lat=float(dep_lat),
        departure_lng=float(dep_lng),
        arrival_lat=float(arr_lat),
        arrival_lng=float(arr_lng),
        status=flight.get("status", "unknown"),
    )
