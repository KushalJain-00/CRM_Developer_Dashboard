"""Tests for EML retry and dead letter queue."""
import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from db.database import Base
from db import eml_models  # noqa
from db.eml_models import EmlJob, EmlJobFile
from services.eml_retry import get_dead_letter_queue, delete_dead_letter, MAX_RETRIES


@pytest_asyncio.fixture
async def eml_engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_dead_letter_empty_on_success(eml_engine):
    async with async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)() as db:
        job = EmlJob(job_name="test", total_files=1, status="completed")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        f = EmlJobFile(job_id=job.id, file_name="test.eml", status="done", attempts=1)
        db.add(f)
        await db.commit()

        dead = await get_dead_letter_queue(job.id, db)
        assert len(dead) == 0


@pytest.mark.asyncio
async def test_dead_letter_catches_max_retries(eml_engine):
    async with async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)() as db:
        job = EmlJob(job_name="test", total_files=1, status="completed")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        f = EmlJobFile(job_id=job.id, file_name="bad.eml", status="failed", attempts=MAX_RETRIES)
        db.add(f)
        await db.commit()

        dead = await get_dead_letter_queue(job.id, db)
        assert len(dead) == 1
        assert dead[0].file_name == "bad.eml"


@pytest.mark.asyncio
async def test_dead_letter_ignores_retryable(eml_engine):
    async with async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)() as db:
        job = EmlJob(job_name="test", total_files=2, status="completed")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        f1 = EmlJobFile(job_id=job.id, file_name="retryable.eml", status="failed", attempts=1)
        f2 = EmlJobFile(job_id=job.id, file_name="dead.eml", status="failed", attempts=MAX_RETRIES)
        db.add_all([f1, f2])
        await db.commit()

        dead = await get_dead_letter_queue(job.id, db)
        assert len(dead) == 1
        assert dead[0].file_name == "dead.eml"


@pytest.mark.asyncio
async def test_abandon_dead_letter(eml_engine):
    async with async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)() as db:
        job = EmlJob(job_name="test", total_files=1, status="completed")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        f = EmlJobFile(job_id=job.id, file_name="bad.eml", status="failed", attempts=MAX_RETRIES)
        db.add(f)
        await db.commit()

        result = await delete_dead_letter(job.id, [f.id], db)
        assert result["deleted"] == 1

        from sqlalchemy import select
        updated = (await db.execute(select(EmlJobFile).where(EmlJobFile.id == f.id))).scalar_one()
        assert updated.status == "abandoned"


@pytest.mark.asyncio
async def test_abandon_empty_list(eml_engine):
    async with async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)() as db:
        job = EmlJob(job_name="test", total_files=0, status="completed")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        result = await delete_dead_letter(job.id, [], db)
        assert result["deleted"] == 0
