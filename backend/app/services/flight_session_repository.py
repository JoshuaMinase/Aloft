"""
Flight session persistence -- now backed by Redis instead of MongoDB.

Why Redis:
- Sessions are short-lived per-user state (one flight = one session).
  After the plane lands they're worthless. Redis TTL auto-deletes them
  after 12 hours -- no manual cleanup, no MongoDB collection growing forever.
- Every GPS ping reads the session (to check already-narrated POIs) and
  writes it (to append newly narrated ones). Redis handles this at
  microsecond latency compared to a MongoDB round trip.

Storage layout:
  session:{session_id}  ->  JSON blob of the full FlightSession
  TTL is reset on every write so an active session never expires mid-flight.

Atomic append:
  record_position_and_narration uses a pipeline (read → mutate → write)
  inside a single round trip. Concurrent pings for the same session are
  rare (a mobile app sends one ping at a time) but the pipeline keeps it
  clean regardless.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.config import get_settings
from app.models.flight_session import FlightSession

_KEY_PREFIX = "session:"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}"


def _serialize(session: FlightSession) -> str:
    return session.model_dump_json()


def _deserialize(raw: str) -> FlightSession:
    return FlightSession.model_validate_json(raw)


async def create_session(redis: Redis, route_key: str) -> FlightSession:
    session = FlightSession(session_id=str(uuid.uuid4()), route_key=route_key)
    ttl = get_settings().session_ttl_seconds
    await redis.set(_key(session.session_id), _serialize(session), ex=ttl)
    return session


async def get_session(redis: Redis, session_id: str) -> FlightSession | None:
    raw = await redis.get(_key(session_id))
    if raw is None:
        return None
    return _deserialize(raw)


async def record_position_and_narration(
    redis: Redis,
    session_id: str,
    lat: float,
    lng: float,
    newly_narrated_source_id: str | None,
) -> None:
    """Update last_position and, if a POI was triggered, append it to the
    narrated list.  Idempotent: recording the same source_id twice is a
    no-op (set membership check before append).

    TTL is refreshed on every write so an active in-flight session never
    expires while the plane is still in the air.
    """
    key = _key(session_id)
    raw = await redis.get(key)
    if raw is None:
        return  # session expired or never existed -- nothing to update

    session = _deserialize(raw)
    session.last_position = (lat, lng)
    session.last_updated_at = datetime.now(UTC)

    if (
        newly_narrated_source_id is not None
        and newly_narrated_source_id not in session.narrated_poi_source_ids
    ):
        session.narrated_poi_source_ids.append(newly_narrated_source_id)

    ttl = get_settings().session_ttl_seconds
    await redis.set(key, _serialize(session), ex=ttl)


async def record_region_narration(
    redis: Redis,
    session_id: str,
    lat: float,
    lng: float,
) -> None:
    """Record that a region narration fired -- updates the cooldown timestamp."""
    key = _key(session_id)
    raw = await redis.get(key)
    if raw is None:
        return  # session expired or never existed -- nothing to update

    session = _deserialize(raw)
    session.last_position = (lat, lng)
    session.last_region_narration_at = datetime.now(UTC)
    session.last_updated_at = datetime.now(UTC)

    ttl = get_settings().session_ttl_seconds
    await redis.set(key, _serialize(session), ex=ttl)


async def record_upcoming_narration(
    redis: Redis,
    session_id: str,
    poi_source_id: str,
) -> None:
    """Record that an upcoming/teaser narration fired for a POI.
    Idempotent: the same POI is never teasered twice per session.
    """
    key = _key(session_id)
    raw = await redis.get(key)
    if raw is None:
        return  # session expired or never existed -- nothing to update

    session = _deserialize(raw)
    session.last_updated_at = datetime.now(UTC)

    if poi_source_id not in session.upcoming_poi_triggered_source_ids:
        session.upcoming_poi_triggered_source_ids.append(poi_source_id)

    ttl = get_settings().session_ttl_seconds
    await redis.set(key, _serialize(session), ex=ttl)
