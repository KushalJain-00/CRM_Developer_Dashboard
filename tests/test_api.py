"""
Unit tests for CRUD auth operations.
"""
import pytest
from crud.auth import upsert_user


@pytest.mark.asyncio
async def test_create_new_user(db_session):
    user = await upsert_user(db_session, email="test@example.com", name="Test User")
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"


@pytest.mark.asyncio
async def test_upsert_existing_user(db_session):
    # Create
    user1 = await upsert_user(db_session, email="upsert@test.com", name="Original")
    original_id = user1.id

    # Upsert
    user2 = await upsert_user(db_session, email="upsert@test.com", name="Updated")
    assert user2.id == original_id
    assert user2.name == "Updated"
