from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """Stored in MongoDB `users` collection.

    `hashed_password` is a bcrypt hash — never the plaintext value.
    `user_id` is the MongoDB _id as a string (set after insert).
    """

    user_id: str = ""  # populated from MongoDB _id after insert
    email: EmailStr
    hashed_password: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserPublic(BaseModel):
    """Safe subset returned to the client — never exposes hashed_password."""

    user_id: str
    email: EmailStr
    is_active: bool
    created_at: datetime
