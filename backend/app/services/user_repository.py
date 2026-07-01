"""
User repository — MongoDB CRUD for the `users` collection.

All functions accept a Motor `AsyncIOMotorDatabase` so they can be called
with a real DB in production and a `mongomock_motor` DB in tests without
any patching.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user import User

logger = logging.getLogger("aloft.services.user_repository")


def _doc_to_user(doc: dict) -> User:
    """Convert a raw MongoDB document to a User model."""
    return User(
        user_id=str(doc["_id"]),
        email=doc["email"],
        hashed_password=doc["hashed_password"],
        is_active=doc.get("is_active", True),
        created_at=doc.get("created_at", datetime.now(UTC)),
    )


async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> User | None:
    """Return the user with this email address, or None if not found."""
    doc = await db.users.find_one({"email": email.lower()})
    return _doc_to_user(doc) if doc else None


async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> User | None:
    """Return the user with this _id string, or None if not found."""
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        oid = ObjectId(user_id)
    except InvalidId:
        return None
    doc = await db.users.find_one({"_id": oid})
    return _doc_to_user(doc) if doc else None


async def create_user(db: AsyncIOMotorDatabase, email: str, hashed_password: str) -> User:
    """Insert a new user and return the created User (with user_id populated).

    Raises ValueError if a user with this email already exists.

    Uses insert_one and catches DuplicateKeyError from the unique index on
    `email` rather than doing a check-then-insert. This avoids the TOCTOU
    race where two concurrent signups with the same email both pass the
    existence check before either has inserted, resulting in one of them
    hitting the unique index with an unhandled 500 instead of the intended 409.
    """
    from pymongo.errors import DuplicateKeyError

    email_lower = email.lower()
    doc = {
        "email": email_lower,
        "hashed_password": hashed_password,
        "is_active": True,
        "created_at": datetime.now(UTC),
    }
    try:
        result = await db.users.insert_one(doc)
    except DuplicateKeyError:
        raise ValueError(f"A user with email '{email_lower}' already exists.")

    logger.info("Created user %s", result.inserted_id)

    return User(
        user_id=str(result.inserted_id),
        email=email_lower,
        hashed_password=hashed_password,
        is_active=True,
        created_at=doc["created_at"],
    )
