"""Tests for EML monitoring endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from main import app
from db.database import get_db


@pytest.fixture(scope="module")
def client(engine):
    test_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with test_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_stats_endpoint(client):
    r = client.get("/api/eml/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "total_jobs" in data["stats"]
    assert "total_files" in data["stats"]
    assert "jobs_by_status" in data["stats"]


def test_throughput_endpoint(client):
    r = client.get("/api/eml/stats/throughput")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "avg_processing_time_ms" in data["throughput"]
    assert "estimated_files_per_hour" in data["throughput"]


def test_errors_endpoint(client):
    r = client.get("/api/eml/stats/errors")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "top_errors" in data["errors"]
    assert "avg_attempts_on_success" in data["errors"]
