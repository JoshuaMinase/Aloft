"""
Authentication router — account creation, login, token refresh, and profile.

Public endpoints (no JWT required):
  POST /auth/signup   — create a new account
  POST /auth/login    — exchange email+password for tokens
  POST /auth/refresh  — exchange a refresh token for a new access token

Protected endpoint (JWT required):
  GET  /auth/me       — return the current user's public profile
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr
from redis.asyncio import Redis

from app.core.dependencies import get_current_user, get_database, rate_limit
from app.core.redis import get_redis as _get_session_redis
from app.models.user import User, UserPublic
from app.services.auth_service import (
    AuthError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    is_refresh_token_revoked,
    revoke_refresh_token,
    verify_password,
)
from app.services.user_repository import create_user, get_user_by_email, get_user_by_id

# Brute-force protection for auth endpoints.
# Login: 20 attempts/hour per IP is generous for legitimate use, blocks password guessing.
# Signup: 10 accounts/hour per IP prevents account-creation spam.
_login_rate_limit = rate_limit("auth_login", max_requests=20, window_seconds=3600, use_user_id=False)
_signup_rate_limit = rate_limit("auth_signup", max_requests=10, window_seconds=3600, use_user_id=False)

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_optional_redis() -> Redis | None:
    """Return the session Redis client, or None if Redis is not configured."""
    try:
        return _get_session_redis()
    except RuntimeError:
        return None


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "passenger@example.com", "password": "strongpassword123"}]
        }
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "passenger@example.com", "password": "strongpassword123"}]
        }
    }


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
    dependencies=[Depends(_signup_rate_limit)],
)
async def signup(
    body: SignupRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TokenResponse:
    """Create a new user account and return access + refresh tokens.

    - Email is stored lowercase and must be unique.
    - Password must be at least 8 characters.
    - Returns tokens immediately — no email verification step (kept simple
      for now; add verification before public launch if desired).

    422 if the email is invalid.
    409 if the email is already registered.
    """
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters.",
        )

    try:
        user = await create_user(db, body.email, hash_password(body.password))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.email),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
    dependencies=[Depends(_login_rate_limit)],
)
async def login(
    body: LoginRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TokenResponse:
    """Authenticate with email + password and receive tokens.

    Returns the same 401 for both "no such user" and "wrong password" —
    deliberately vague to avoid leaking whether an email is registered.
    """
    _WRONG_CREDS = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await get_user_by_email(db, body.email)
    if user is None:
        raise _WRONG_CREDS

    if not verify_password(body.password, user.hashed_password):
        raise _WRONG_CREDS

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.email),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new access token",
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TokenResponse:
    """Exchange a valid refresh token for a fresh access token + refresh token.

    Both tokens are rotated on every refresh. The old refresh token's JTI is
    added to a Redis blocklist so it cannot be reused — true single-use
    rotation. If Redis is unavailable the revocation is skipped (fails open)
    so a Redis outage never locks users out.

    401 if the refresh token is expired, tampered, the wrong type, or has
    already been used (JTI found in the blocklist).
    401 if the user no longer exists or is deactivated.
    """
    try:
        payload = decode_refresh_token(body.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    jti: str = payload.get("jti", "")
    exp: int = payload.get("exp", 0)
    user_id: str = payload["sub"]

    redis = _get_optional_redis()
    if await is_refresh_token_revoked(redis, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has already been used. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Revoke the used token before issuing the new one
    await revoke_refresh_token(redis, jti, exp)

    return TokenResponse(
        access_token=create_access_token(user.user_id, user.email),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get the current user's profile",
)
async def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Return the authenticated user's public profile.

    Requires a valid access token in `Authorization: Bearer <token>`.
    """
    return UserPublic(
        user_id=current_user.user_id,
        email=current_user.email,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )