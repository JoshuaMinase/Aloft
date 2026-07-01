from __future__ import annotations

import json
import logging
import logging.config
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import close_mongo_connection, connect_to_mongo
from app.core.redis import close_redis_connection, connect_to_redis
from app.core.redis_client import (
    close_redis_connection as close_rate_limit_redis,
)
from app.core.redis_client import (
    connect_to_redis as connect_rate_limit_redis,
)
from app.routers import audio, auth, content, download, flights, images, pois, sessions, stories

# ---------------------------------------------------------------------------
# Structured JSON logging (production) / plain text (development)
# ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line.

    Fields: timestamp (ISO-8601), level, logger, message, plus any extra
    fields attached via LogRecord. In production these land in whatever log
    aggregator is consuming stdout (CloudWatch, Datadog, Loki, etc.) and are
    immediately searchable/filterable without regex parsing.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Include any extra fields added via `logger.info("...", extra={...})`
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                try:
                    json.dumps(value)  # only include JSON-serialisable extras
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    """Set up the root logger.

    - ENVIRONMENT=production  → JSON formatter to stdout (log aggregator friendly)
    - Any other value         → human-readable format to stdout (dev/test friendly)

    Either way, the log level is controlled by LOG_LEVEL (default INFO).
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.environment.lower() == "production":
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(level)

    # Quiet down noisy third-party loggers that aren't useful in production
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)


_configure_logging()
logger = logging.getLogger("aloft.main")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await connect_to_mongo()
    await connect_to_redis()
    # Rate-limit Redis is optional -- connect_rate_limit_redis() is a no-op
    # if REDIS_URL isn't configured, and rate limiting fails open without it.
    await connect_rate_limit_redis()
    app.state.http_client = httpx.AsyncClient()

    # SEC-5: Warn loudly when the default JWT secret is in use in any environment.
    # In production this is caught by config.py's model_validator and raises at
    # Settings construction time. Here we catch the development case where the
    # default is still in use -- tokens signed with a known public default are
    # trivially forgeable by anyone who reads this codebase.
    _JWT_DEFAULT = "change-me-in-production-use-secrets-token-hex-32"
    if settings.jwt_secret_key.get_secret_value() == _JWT_DEFAULT:
        logger.warning(
            "JWT_SECRET_KEY is set to the insecure default value. "
            "All tokens are trivially forgeable. "
            "Set a strong random secret in your .env file: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    logger.info(
        "Aloft backend started",
        extra={"environment": settings.environment, "log_level": settings.log_level},
    )
    yield
    await app.state.http_client.aclose()
    await close_rate_limit_redis()
    await close_redis_connection()
    await close_mongo_connection()
    logger.info("Aloft backend shut down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aloft",
    version="0.1.0",
    description=(
        "Aloft turns any commercial flight into a live audio tour.\n\n"
        "**Authentication:**\n"
        "All endpoints except `/health`, `POST /auth/signup`, `POST /auth/login`, "
        "and `POST /auth/refresh` require a valid JWT access token.\n"
        "Include it as `Authorization: Bearer <token>`.\n\n"
        "**Core flow:**\n"
        "1. `POST /auth/signup` or `POST /auth/login` — get tokens\n"
        "2. `POST /routes/pois` — discover points of interest along a route\n"
        "3. `POST /routes/{route_key}/content` — generate stories + audio for every POI\n"
        "4. `POST /sessions` — start a live session\n"
        "5. `POST /sessions/{session_id}/position` — send GPS position, get narration triggers\n\n"
        "**Or, all-in-one by flight number:**\n"
        "`POST /flights/{flight_iata}/pois` — looks up the route via AviationStack then runs step 2."
    ),
    contact={"name": "Aloft", "email": get_settings().app_contact_email},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)
app.include_router(auth.router)
app.include_router(pois.router)
app.include_router(stories.router)
app.include_router(audio.router)
app.include_router(flights.router)
app.include_router(images.router)
app.include_router(content.router)
app.include_router(download.router)
app.include_router(sessions.router)


@app.get("/health", tags=["meta"], summary="Health check")
async def health() -> dict[str, str]:
    """Returns `{"status": "ok"}` when the service is running.

    Suitable for use as a load balancer or container health check probe.
    Does not check downstream services (MongoDB, Redis) — use this only
    to verify the process is alive and accepting HTTP.
    For a full readiness check including downstream liveness, use GET /health/ready.
    """
    return {"status": "ok"}


@app.get("/health/ready", tags=["meta"], summary="Readiness check — includes downstream liveness")
async def health_ready() -> dict:
    """Checks that MongoDB and Redis are reachable.

    Returns 200 with per-service status when all required services are up.
    Returns 503 if any required service is unreachable.

    Use this for Kubernetes readiness probes or deployment smoke tests.
    Redis failure is reported but does not cause a 503 because Redis is
    optional infrastructure (rate limiting and sessions degrade gracefully).
    """
    from app.core.db import get_db
    from app.core.redis import get_redis as _get_session_redis

    result: dict = {"mongodb": "unknown", "redis": "unknown"}
    failed = False

    # MongoDB check
    try:
        db = get_db()
        await db.command("ping")
        result["mongodb"] = "ok"
    except Exception as exc:
        result["mongodb"] = f"error: {exc}"
        failed = True

    # Redis check (optional — failure is reported but not fatal)
    try:
        redis = _get_session_redis()
        await redis.ping()
        result["redis"] = "ok"
    except RuntimeError:
        # Redis not configured — expected in minimal dev setups
        result["redis"] = "not configured"
    except Exception as exc:
        result["redis"] = f"error: {exc}"
        # Redis is optional; don't fail the readiness check for it

    if failed:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "degraded", **result})

    return {"status": "ok", **result}
