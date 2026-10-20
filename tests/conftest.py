"""
Test configuration and fixtures for CRM backend tests.
"""
import pytest
import pytest_asyncio
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.database import Base, get_db
from db import models  # noqa — registers models with Base
from main import app
from core.auth import verify_token


async def _fake_user():
    # ponytail: tests skip real Supabase auth via dependency_overrides
    return type("User", (), {"email": "test@example.com", "id": 1})()


app.dependency_overrides[verify_token] = _fake_user


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test database engine (in-memory SQLite)."""
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Create a fresh database session for each test."""
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client(engine):
    """TestClient whose get_db dependency yields sessions from the test engine."""
    # ponytail: same session-scoped engine as db_session so ORM seeds and API
    # requests see one shared in-memory DB (StaticPool = single connection)
    async def _get_db():
        maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
