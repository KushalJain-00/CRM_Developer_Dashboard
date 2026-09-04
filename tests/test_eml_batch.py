"""Tests for batch processing and checkpointing."""
import asyncio
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.database import Base
from db import eml_models  # noqa
from services.eml_batch import process_job_optimized

SAMPLE_EML = b"""From: Test <test@example.com>
To: recipient@example.com
Subject: Test
Date: Mon, 01 Jan 2024 10:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Hello

Regards,
Test User
Manager
ABC Corp
+91 9876543210
"""


@pytest_asyncio.fixture
async def eml_engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


def _write_files(staging: Path, files: list[tuple[str, bytes]]):
    """Write (name, data) tuples to a staging directory."""
    staging.mkdir(parents=True, exist_ok=True)
    for name, data in files:
        (staging / name).write_bytes(data)


@pytest.mark.asyncio
async def test_batch_processes_files(eml_engine, tmp_path):
    """Verify batch processor handles multiple files and marks them done."""
    session_factory = async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        job = eml_models.EmlJob(job_name="test-batch", total_files=2, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    staging = tmp_path / "batch1"
    _write_files(staging, [("test1.eml", SAMPLE_EML), ("test2.eml", SAMPLE_EML)])

    with patch("services.eml_batch.AsyncSessionLocal", session_factory):
        await process_job_optimized(job_id, str(staging))

    async with session_factory() as db:
        result = await db.execute(select(eml_models.EmlJob).where(eml_models.EmlJob.id == job_id))
        job_row = result.scalar_one()
        assert job_row.status == "completed"
        assert job_row.succeeded == 2
        assert job_row.processed == 2

        result = await db.execute(select(eml_models.EmlJobFile).where(eml_models.EmlJobFile.job_id == job_id))
        file_rows = result.scalars().all()
        assert len(file_rows) == 2
        assert all(f.status == "done" for f in file_rows)


@pytest.mark.asyncio
async def test_batch_skips_already_processed(eml_engine, tmp_path):
    """Resume support: files already marked 'done' are skipped."""
    session_factory = async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        job = eml_models.EmlJob(job_name="resume-test", total_files=3, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

        done_file = eml_models.EmlJobFile(
            job_id=job_id, file_name="already_done.eml", status="done", attempts=1
        )
        db.add(done_file)
        await db.commit()

    staging = tmp_path / "batch2"
    _write_files(staging, [
        ("already_done.eml", SAMPLE_EML),
        ("new1.eml", SAMPLE_EML),
        ("new2.eml", SAMPLE_EML),
    ])

    with patch("services.eml_batch.AsyncSessionLocal", session_factory):
        await process_job_optimized(job_id, str(staging))

    async with session_factory() as db:
        result = await db.execute(select(eml_models.EmlJobFile).where(eml_models.EmlJobFile.job_id == job_id))
        file_rows = result.scalars().all()
        assert len(file_rows) == 3
        done_count = sum(1 for f in file_rows if f.file_name == "already_done.eml")
        assert done_count == 1


@pytest.mark.asyncio
async def test_batch_marks_failed_files(eml_engine, tmp_path):
    """Files that error during parsing are marked failed, not done."""
    session_factory = async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        job = eml_models.EmlJob(job_name="fail-test", total_files=1, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    staging = tmp_path / "batch3"
    _write_files(staging, [("bad.eml", b"not a real eml")])

    with patch("services.eml_batch.AsyncSessionLocal", session_factory), \
         patch("services.eml_batch.parse_eml_bytes", side_effect=RuntimeError("parse bomb")):
        await process_job_optimized(job_id, str(staging))

    async with session_factory() as db:
        result = await db.execute(select(eml_models.EmlJob).where(eml_models.EmlJob.id == job_id))
        job_row = result.scalar_one()
        assert job_row.failed == 1
        assert job_row.succeeded == 0

        result = await db.execute(select(eml_models.EmlJobFile).where(eml_models.EmlJobFile.job_id == job_id))
        file_row = result.scalar_one()
        assert file_row.status == "failed"
        assert "parse bomb" in file_row.error


@pytest.mark.asyncio
async def test_batch_cancellation(eml_engine, tmp_path):
    """If job is cancelled mid-batch, processing stops."""
    session_factory = async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        job = eml_models.EmlJob(job_name="cancel-test", total_files=5, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    staging = tmp_path / "batch4"
    _write_files(staging, [(f"file{i}.eml", SAMPLE_EML) for i in range(5)])

    with patch("services.eml_batch.AsyncSessionLocal", session_factory), \
         patch("services.eml_batch.CHECKPOINT_INTERVAL", 1):

        async def cancel_after_delay():
            await asyncio.sleep(0.05)
            async with session_factory() as db:
                await db.execute(
                    update(eml_models.EmlJob).where(eml_models.EmlJob.id == job_id).values(status="cancelled")
                )
                await db.commit()

        await asyncio.gather(
            process_job_optimized(job_id, str(staging)),
            cancel_after_delay(),
        )

    async with session_factory() as db:
        result = await db.execute(select(eml_models.EmlJob).where(eml_models.EmlJob.id == job_id))
        job_row = result.scalar_one()
        assert job_row.status == "cancelled"
