"""Tests for EML database models."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.database import Base
from db import eml_models  # noqa


@pytest_asyncio.fixture
async def eml_engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_create_eml_job(eml_engine):
    async_session = async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        job = eml_models.EmlJob(job_name="test-batch", total_files=100)
        session.add(job)
        await session.commit()
        assert job.id is not None
        assert job.status == "pending"
        assert job.total_files == 100


@pytest.mark.asyncio
async def test_create_eml_job_file(eml_engine):
    async_session = async_sessionmaker(bind=eml_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        job = eml_models.EmlJob(job_name="test", total_files=1)
        session.add(job)
        await session.commit()

        file_record = eml_models.EmlJobFile(
            job_id=job.id,
            file_name="email_001.eml",
            status="pending"
        )
        session.add(file_record)
        await session.commit()
        assert file_record.id is not None
        assert file_record.job_id == job.id
