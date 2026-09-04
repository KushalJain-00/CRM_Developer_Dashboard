"""
Error retry and dead letter queue for EML pipeline.
"""
import asyncio
import logging
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.eml_models import EmlJob, EmlJobFile

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 15]  # seconds, exponential-ish backoff


async def retry_failed_files(job_id: UUID, db: AsyncSession):
    """Retry all failed files in a job (up to MAX_RETRIES attempts each).

    Requires the job's raw file contents to be re-provided via the API.
    Without them, files are marked as failed with a descriptive error.
    """
    result = await db.execute(
        select(EmlJobFile).where(
            EmlJobFile.job_id == job_id,
            EmlJobFile.status == "failed",
            EmlJobFile.attempts < MAX_RETRIES,
        )
    )
    files_to_retry = result.scalars().all()

    if not files_to_retry:
        return {"retried": 0, "message": "No files eligible for retry"}

    retried = 0
    for file_record in files_to_retry:
        attempt = file_record.attempts + 1
        delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]

        logger.info("Retrying %s (attempt %d, delay %ds)", file_record.file_name, attempt, delay)

        file_record.status = "retrying"
        file_record.attempts = attempt
        await db.commit()

        await asyncio.sleep(delay)

        # Raw bytes aren't persisted — real retry requires re-upload via API
        file_record.status = "failed"
        file_record.error = f"Retry attempt {attempt} failed — raw file not available"
        await db.commit()

        retried += 1

    return {"retried": retried, "message": f"Retried {retried} files"}


async def get_dead_letter_queue(job_id: UUID, db: AsyncSession):
    """Get files that have exhausted all retries."""
    result = await db.execute(
        select(EmlJobFile).where(
            EmlJobFile.job_id == job_id,
            EmlJobFile.status == "failed",
            EmlJobFile.attempts >= MAX_RETRIES,
        ).order_by(EmlJobFile.updated_at.desc())
    )
    return result.scalars().all()


async def delete_dead_letter(job_id: UUID, file_ids: list[UUID], db: AsyncSession):
    """Mark dead letter files as abandoned (give up on them)."""
    await db.execute(
        update(EmlJobFile).where(
            EmlJobFile.job_id == job_id,
            EmlJobFile.id.in_(file_ids),
        ).values(status="abandoned")
    )
    await db.commit()
    return {"deleted": len(file_ids)}
