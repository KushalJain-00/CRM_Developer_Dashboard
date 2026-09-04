"""Integration test for the full EML pipeline."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from main import app
from db.database import get_db


SAMPLE_EML = b"""From: Test User <test@example.com>
To: recipient@example.com
Subject: Test Email
Date: Mon, 01 Jan 2024 10:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Hello,

This is a test email.

Regards,

Test User
Manager
Example Corp
+91 9876543210
"""


@pytest.fixture(scope="module")
def client(engine):
    test_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with test_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Patch AsyncSessionLocal in the pipeline module so background tasks
    # use the test DB instead of the production one.
    with patch("api.eml_pipeline.AsyncSessionLocal", test_factory):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    app.dependency_overrides.clear()


def test_upload_and_poll(client):
    r = client.post(
        "/api/eml/upload",
        files=[("files", ("test.eml", SAMPLE_EML, "message/rfc822"))],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    job_id = data["job_id"]

    r = client.get(f"/api/eml/jobs/{job_id}")
    assert r.status_code == 200
    job = r.json()["job"]
    assert job["status"] == "completed"
    assert job["total_files"] == 1
    assert job["succeeded"] == 1


def test_upload_no_valid_files(client):
    r = client.post(
        "/api/eml/upload",
        files=[("files", ("readme.txt", b"not an eml file", "text/plain"))],
    )
    assert r.status_code == 400


def test_list_jobs(client):
    r = client.get("/api/eml/jobs")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["jobs"], list)


def test_get_nonexistent_job(client):
    r = client.get("/api/eml/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_cancel_nonexistent_job(client):
    r = client.post("/api/eml/jobs/00000000-0000-0000-0000-000000000000/cancel")
    assert r.status_code == 404
