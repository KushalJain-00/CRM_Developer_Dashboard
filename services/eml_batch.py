"""
Batch processing engine for EML pipeline.
Optimized for throughput: bulk inserts, checkpointing, resume support.
"""
import time
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from db.database import AsyncSessionLocal
from db.eml_models import EmlJob, EmlJobFile
from services.eml_parser import parse_eml_bytes
from services.eml_signature import extract_signature
from services.eml_dedup import deduplicate_contacts

logger = logging.getLogger(__name__)

CHECKPOINT_INTERVAL = 50  # commit progress every N files


async def process_job_optimized(job_id: UUID, file_contents: list[tuple[str, bytes]]):
    """Optimized batch processor with checkpointing and resume support.

    Compared to process_job_background:
    - Skips already-processed files on resume
    - Batches EmlJobFile inserts (no per-file flush)
    - Commits at CHECKPOINT_INTERVAL boundaries
    - Same cancellation + error handling semantics
    """
    async with AsyncSessionLocal() as db:
        # Mark processing
        await db.execute(
            update(EmlJob).where(EmlJob.id == job_id).values(status="processing")
        )
        await db.commit()

        # Resume support — skip files that already completed
        result = await db.execute(
            select(EmlJobFile.file_name).where(
                EmlJobFile.job_id == job_id,
                EmlJobFile.status == "done",
            )
        )
        processed_names = {row[0] for row in result.fetchall()}
        remaining = [(n, d) for n, d in file_contents if n not in processed_names]

        if processed_names:
            logger.info(
                "Resuming job %s: %d already processed, %d remaining",
                job_id, len(processed_names), len(remaining),
            )

        file_records_pending: list[EmlJobFile] = []

        try:
            for i, (file_name, raw_bytes) in enumerate(remaining):
                # Check cancellation
                job = (await db.execute(
                    select(EmlJob).where(EmlJob.id == job_id)
                )).scalar_one_or_none()
                if not job or job.status == "cancelled":
                    # Flush any pending records before exiting
                    if file_records_pending:
                        db.add_all(file_records_pending)
                        await db.commit()
                    return

                t0 = time.monotonic()
                file_record = EmlJobFile(
                    job_id=job_id, file_name=file_name, status="parsing"
                )

                try:
                    parsed = parse_eml_bytes(raw_bytes, file_name)
                    sig_data = extract_signature(
                        parsed.body_text, parsed.html_body,
                        parsed.from_name, parsed.from_email,
                    )

                    confidence = sig_data.get("confidence", 0)
                    method = "deterministic" if confidence >= 60 else "heuristic"

                    file_record.status = "done"
                    file_record.extraction_method = method
                    file_record.confidence = confidence
                    file_record.extracted_data = sig_data
                    file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)
                    file_record.attempts = 1

                    job.succeeded += 1
                    if method.startswith("ai"):
                        job.ai_enriched += 1

                except Exception as e:
                    file_record.status = "failed"
                    file_record.error = str(e)[:2000]
                    file_record.attempts = 1
                    file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)
                    job.failed += 1
                    logger.warning("EML file %s failed: %s", file_name, e)

                job.processed += 1
                file_records_pending.append(file_record)

                # Checkpoint — bulk insert + commit every CHECKPOINT_INTERVAL files
                if len(file_records_pending) >= CHECKPOINT_INTERVAL:
                    db.add_all(file_records_pending)
                    await db.commit()
                    file_records_pending = []
                    logger.info(
                        "Job %s: %d/%d processed",
                        job_id, i + 1, len(remaining),
                    )

            # Flush remaining
            if file_records_pending:
                db.add_all(file_records_pending)
                await db.commit()

            # Finalize
            job = (await db.execute(
                select(EmlJob).where(EmlJob.id == job_id)
            )).scalar_one_or_none()
            if job and job.status != "cancelled":
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()

        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)
            job = (await db.execute(
                select(EmlJob).where(EmlJob.id == job_id)
            )).scalar_one_or_none()
            if job:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
