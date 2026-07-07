"""
Shared pytest fixtures for all router tests.

auth_override
─────────────
Overrides `get_current_user` in `app.dependency_overrides` with a fixture
that returns a fake User without hitting the database or validating a JWT.

Every router test fixture that builds a TestClient must include
`auth_override` to prevent 401s on protected endpoints.

Usage in a test file:
    @pytest.fixture
    def test_client(mongomock_db, auth_override) -> Iterator[TestClient]:
        app.dependency_overrides[get_database] = lambda: mongomock_db
        app.dependency_overrides[get_http_client] = lambda: httpx.AsyncClient()
        yield TestClient(app)
        app.dependency_overrides.clear()

The `auth_override` fixture installs the override before the test client is
created and tears it down after via its own cleanup — but clearing
`app.dependency_overrides` in the test_client fixture's teardown covers it
too, so either pattern is safe.
"""

from __future__ import annotations

import pytest

from app.core.dependencies import get_current_user
from app.main import app
from app.models.role import Role
from app.models.user import User

_FAKE_USER = User(
    user_id="000000000000000000000001",
    email="testuser@example.com",
    hashed_password="$2b$12$fakehashfortesting",
    is_active=True,
    is_verified=True,
    role=Role.USER,
)


@pytest.fixture
def auth_override():
    """Install a no-op get_current_user override, then remove it after the test."""
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    yield _FAKE_USER
    app.dependency_overrides.pop(get_current_user, None)
