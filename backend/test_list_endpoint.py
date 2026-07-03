"""Quick test for the /v1/routes/list endpoint"""
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from app.main import app
from app.core.db import ensure_indexes
from app.core.dependencies import get_database, get_current_user
from unittest.mock import AsyncMock, patch
from app.models.user import User

# Setup test database
client = AsyncMongoMockClient()
db = client["test_aloft"]

# Override dependencies
def override_get_database():
    return db

def override_get_current_user():
    return User(
        user_id="test_id", 
        email="test@example.com", 
        hashed_password="test_hash",
        is_verified=True
    )

app.dependency_overrides[get_database] = override_get_database
app.dependency_overrides[get_current_user] = override_get_current_user

test_client = TestClient(app)

# Add some test POIs
import asyncio
async def setup_test_data():
    await ensure_indexes(db)
    test_poi = {
        "source_id": "wikipedia:123",
        "name": "Test POI",
        "location": {"type": "Point", "coordinates": [0, 0]},
        "source": "wikipedia",
        "updated_at": "2024-01-01T00:00:00"
    }
    await db.pois.insert_one(test_poi)

asyncio.run(setup_test_data())

# Test the endpoint
response = test_client.get("/v1/routes/list?page=1&page_size=10&sort_by=updated_at&sort_order=desc")
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
