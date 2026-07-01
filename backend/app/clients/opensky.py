"""
OpenSky Network client — live ADS-B aircraft position lookup.

Queries the OpenSky REST API for the current position of an aircraft
by its ICAO 24-bit transponder address or callsign.

API docs: https://openskynetwork.github.io/opensky-api/rest.html

No API key required for anonymous access (rate-limited to ~100 requests
per day per IP). Using a free OpenSky account credential raises the limit
to ~4,000 requests/day. Set OPENSKY_USERNAME and OPENSKY_PASSWORD in .env
to use authenticated access.

The endpoint we use:
  GET https://opensky-network.org/api/states/all
    ?icao24=<hex>    (filter by transponder address)
    &callsign=<str>  (filter by callsign, padded to 8 chars)

Response schema (relevant fields from the state vector):
  index 0:  icao24   — ICAO 24-bit transponder address (hex string)
  index 1:  callsign — flight callsign (8-char padded string or null)
  index 5:  longitude  (float or null)
  index 6:  latitude   (float or null)
  index 7:  baro_altitude (metres, float or null)
  index 9:  velocity (m/s, float or null)
  index 10: true_track (degrees, float or null)
  index 11: vertical_rate (m/s, float or null)
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger("aloft.clients.opensky")

_BASE_URL = "https://opensky-network.org/api"
_STATES_ENDPOINT = f"{_BASE_URL}/states/all"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 2.0


class AircraftPosition(BaseModel):
    """Current position of an aircraft from the OpenSky live feed."""

    icao24: str
    callsign: str | None
    latitude: float
    longitude: float
    baro_altitude_m: float | None = None
    velocity_ms: float | None = None
    true_track_deg: float | None = None
    vertical_rate_ms: float | None = None
    on_ground: bool = False


class OpenSkyClientError(Exception):
    """Raised when the OpenSky API request fails after retries."""


class AircraftNotFoundError(OpenSkyClientError):
    """Raised when the aircraft is not currently visible in the OpenSky feed.

    This is normal — the aircraft may be on the ground, out of ADS-B
    coverage, or the transponder may be off. Callers should treat this
    as a soft failure and fall back to client-provided GPS.
    """


def _parse_state_vector(state: list) -> AircraftPosition | None:
    """Parse a single OpenSky state vector list into an AircraftPosition.

    Returns None if the aircraft has no position fix (lat/lng are null).
    """
    try:
        lat = state[6]
        lng = state[5]
        if lat is None or lng is None:
            return None

        callsign_raw = state[1]
        callsign = callsign_raw.strip() if callsign_raw else None

        return AircraftPosition(
            icao24=state[0],
            callsign=callsign or None,
            latitude=float(lat),
            longitude=float(lng),
            baro_altitude_m=float(state[7]) if state[7] is not None else None,
            velocity_ms=float(state[9]) if state[9] is not None else None,
            true_track_deg=float(state[10]) if state[10] is not None else None,
            vertical_rate_ms=float(state[11]) if state[11] is not None else None,
            on_ground=bool(state[8]) if state[8] is not None else False,
        )
    except (IndexError, TypeError, ValueError):
        return None


async def get_aircraft_position(
    client: httpx.AsyncClient,
    *,
    icao24: str | None = None,
    callsign: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> AircraftPosition:
    """Look up the current live position of an aircraft.

    Exactly one of `icao24` or `callsign` must be provided.

    Args:
        client: shared httpx AsyncClient.
        icao24: ICAO 24-bit transponder address in hex (e.g. "4b1806").
            Most reliable identifier — unique per aircraft, never changes.
        callsign: Flight callsign (e.g. "ET308"). Padded to 8 chars
            per the OpenSky API requirement.
        username: Optional OpenSky account username for higher rate limits.
        password: Optional OpenSky account password.

    Returns:
        AircraftPosition with the current lat/lng and speed/heading.

    Raises:
        AircraftNotFoundError: aircraft not visible in OpenSky feed right now.
        OpenSkyClientError: network failure or API error after retries.
        ValueError: neither or both of icao24/callsign were provided.
    """
    if not icao24 and not callsign:
        raise ValueError("Provide either icao24 or callsign.")
    if icao24 and callsign:
        raise ValueError("Provide icao24 or callsign, not both.")

    params: dict[str, str] = {}
    if icao24:
        params["icao24"] = icao24.lower()
    if callsign:
        # OpenSky pads callsigns to exactly 8 characters
        params["callsign"] = callsign.upper().ljust(8)

    auth = (username, password) if username and password else None

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.get(
                _STATES_ENDPOINT,
                params=params,
                auth=auth,
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
                headers={"User-Agent": "AloftFlightNarrationApp/0.1"},
            )
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning(
                "OpenSky network error attempt %d/%d: %s", attempt, _MAX_ATTEMPTS, exc
            )
        else:
            if response.status_code == 200:
                data = response.json()
                states = data.get("states") or []
                if not states:
                    raise AircraftNotFoundError(
                        f"Aircraft not found in OpenSky feed "
                        f"(icao24={icao24!r}, callsign={callsign!r}). "
                        "The aircraft may be on the ground, out of ADS-B coverage, "
                        "or the transponder may be off."
                    )
                # Take the first matching state vector
                position = _parse_state_vector(states[0])
                if position is None:
                    raise AircraftNotFoundError(
                        f"Aircraft found in OpenSky feed but has no position fix "
                        f"(icao24={icao24!r}, callsign={callsign!r})."
                    )
                logger.debug(
                    "OpenSky position for %s: lat=%.4f lng=%.4f",
                    icao24 or callsign,
                    position.latitude,
                    position.longitude,
                )
                return position

            if response.status_code == 404:
                raise AircraftNotFoundError(
                    f"Aircraft not found (HTTP 404) for "
                    f"icao24={icao24!r}, callsign={callsign!r}."
                )
            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_error = OpenSkyClientError(
                    f"OpenSky returned HTTP {response.status_code}"
                )
                logger.warning(
                    "OpenSky retryable error %d, attempt %d/%d",
                    response.status_code,
                    attempt,
                    _MAX_ATTEMPTS,
                )
            else:
                raise OpenSkyClientError(
                    f"OpenSky non-retryable HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )

        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    raise OpenSkyClientError(
        f"OpenSky request failed after {_MAX_ATTEMPTS} attempts"
    ) from last_error
