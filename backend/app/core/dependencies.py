"""
Shared FastAPI dependency functions, used across multiple routers.

Kept in one place so there's exactly one definition of "how do I get the
shared HTTP client," "how do I get the database," "how do I get the current
authenticated user," etc.

AUTH MODEL
══════════
Authentication uses stateless JWT bearer tokens:

  POST /auth/signup  → create account → returns {access_token, refresh_token}
  POST /auth/login   → verify password → returns {access_token, refresh_token}
  POST /auth/refresh → exchange refresh token for new access token

All protected routes call `get_current_user` as a dependency, which:
  1. Reads the Authorization: Bearer <token> header.
  2. Decodes + validates the JWT (signature, expiry, type claim).
  3. Looks up the user_id in MongoDB to confirm the account exists + is active.
  4. Returns the User model — available in the endpoint as a parameter.

Public endpoints (no auth required):
  GET  /health
  POST /auth/signup
  POST /auth/login
  POST /auth/refresh

Everything else requires a valid access token.

Rate limits key by user_id for authenticated endpoints (where the user is resolved),
falling back to IP for public endpoints.
"""

from __future__ import annotations

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.db import get_db
from app.core.redis import get_redis as _get_session_redis
from app.core.redis_client import get_redis as _get_rate_limit_redis
from app.models.user import User
from app.services.auth_service import AuthError, decode_access_token
from app.services.rate_limiter import RateLimitExceeded, check_rate_limit
from app.services.user_repository import get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False)


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Pulled from app.state — one shared connection pool across every request."""
    return request.app.state.http_client


def get_database() -> AsyncIOMotorDatabase:
    return get_db()


def get_redis() -> Redis:
    """Returns the session Redis client (core/redis.py).

    Used by the sessions router for flight session storage. Raises if
    Redis isn't connected — sessions require Redis, unlike rate limiting.
    """
    return _get_session_redis()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> User:
    """FastAPI dependency that validates a JWT Bearer token and returns the User.

    Usage in a router endpoint:
        async def my_endpoint(_: User = Depends(get_current_user)):
            ...

    Raises HTTP 401 if:
      - No Authorization header is present.
      - The token is expired, tampered, or the wrong type.
      - The user_id in the token no longer exists or is deactivated.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Include 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def rate_limit(name: str, max_requests: int, window_seconds: int, use_user_id: bool = False):
    """Builds a FastAPI dependency enforcing rate limiting.

    Args:
        name: Rate limit identifier (used in Redis key).
        max_requests: Maximum requests allowed in the window.
        window_seconds: Time window in seconds.
        use_user_id: If True, key by authenticated user_id instead of IP.
            For authenticated endpoints, this provides fairer per-user limits.
            IP-based limiting is used for public endpoints.

    Backed by the optional Redis client (core/redis_client.py). Fails open if
    Redis isn't configured — rate limiting is a protection layer, never a
    reason the app can't start or a test can't run.
    """

    async def dependency(
        request: Request,
        user: User | None = Depends(_get_user_if_authenticated),
    ) -> None:
        if use_user_id and user is not None:
            key = f"ratelimit:{name}:user:{user.user_id}"
        else:
            client_ip = request.client.host if request.client else "unknown"
            key = f"ratelimit:{name}:{client_ip}"
        try:
            redis_client = _get_rate_limit_redis()
        except RuntimeError:
            redis_client = None

        try:
            await check_rate_limit(redis_client, key, max_requests, window_seconds)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded for this operation. "
                    f"Try again in {exc.retry_after_seconds} seconds."
                ),
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc

    return dependency


async def _get_user_if_authenticated(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> User | None:
    """Lightweight user lookup for rate limiting purposes.

    Returns the User if authenticated (valid token + active account),
    or None if not authenticated. Does NOT raise 401 for missing auth.
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except AuthError:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        return None

    return user


def flight_lookup_rate_limit():
    """Rate limit dependency for POST /flights/{flight_iata}/pois.

    AviationStack's free tier caps around 100 requests/month total.
    Uses IP-based limiting since this endpoint is public.
    """
    settings = get_settings()
    return rate_limit(
        "flights",
        max_requests=settings.rate_limit_flight_lookups_per_hour,
        window_seconds=3600,
        use_user_id=False,
    )


def content_generation_rate_limit():
    """Rate limit dependency for POST /routes/{route_key}/content.

    A single call here can fire dozens of Groq calls (one per POI),
    and Groq's free tier caps around 30 requests/min.
    Uses per-user limiting for fairness.
    """
    settings = get_settings()
    return rate_limit(
        "content",
        max_requests=settings.rate_limit_content_generation_per_hour,
        window_seconds=3600,
        use_user_id=True,
    )


def position_update_rate_limit():
    """Rate limit dependency for POST /sessions/{id}/position.

    The mobile app calls this every few seconds during a flight.
    The limit is generous (600/min = 10/sec) — enough for any realistic
    polling interval while blocking runaway loops or abuse.
    Uses per-user limiting since this is an authenticated endpoint.
    """
    settings = get_settings()
    return rate_limit(
        "position",
        max_requests=settings.rate_limit_position_updates_per_minute,
        window_seconds=60,
        use_user_id=True,
    )