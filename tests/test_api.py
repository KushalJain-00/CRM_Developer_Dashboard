"""
Integration tests for /api/auth/upsert (upsert logic lives in api/auth.py).
"""
import pytest
from db.models import User


def test_create_new_user(client):
    r = client.post("/api/auth/upsert", json={"email": "test@example.com", "name": "Test User"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["email"] == "test@example.com"
    assert body["user_id"] is not None


@pytest.mark.asyncio
async def test_upsert_existing_user(client, db_session):
    # Create
    r1 = client.post("/api/auth/upsert", json={"email": "upsert@test.com", "name": "Original"})
    original_id = r1.json()["user_id"]

    # Upsert
    r2 = client.post("/api/auth/upsert", json={"email": "upsert@test.com", "name": "Updated"})
    assert r2.json()["user_id"] == original_id

    user = await db_session.get(User, original_id)
    assert user.name == "Updated"
