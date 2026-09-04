"""EML Pipeline API — upload, process, and track .eml file batches."""
import time
import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from db.database import get_db, AsyncSessionLocal
from db.eml_models import EmlJob, EmlJobFile
from services.eml_parser import parse_eml_bytes
from services.eml_signature import extract_signature
from services.eml_dedup import deduplicate_contacts

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eml-pipeline"])


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

async def _call_ai_enrichment(sig_data: dict, body_text: str, html_body: str) -> dict | None:
    """Placeholder for Phase 2 AI enrichment."""
    return None


def _route_to_status(sig_data: dict, ai_result: dict | None) -> str:
    """Determine extraction_method from results."""
    if ai_result:
        return "ai_extract"
    confidence = sig_data.get("confidence", 0)
    if confidence >= 60:
        return "deterministic"
    return "heuristic"


async def process_job_background(job_id: UUID, file_contents: list[tuple[str, bytes]]):
    """Process all files in a job. Runs as a background task with its own DB session."""
    async with AsyncSessionLocal() as db:
        # Mark job as processing
        await db.execute(
            update(EmlJob).where(EmlJob.id == job_id).values(status="processing")
        )
        await db.commit()

        batch_size = 50
        try:
            for batch_start in range(0, len(file_contents), batch_size):
                batch = file_contents[batch_start:batch_start + batch_size]

                # Check for cancellation
                job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
                if not job or job.status == "cancelled":
                    return

                contacts_batch = []

                for file_name, raw_bytes in batch:
                    t0 = time.monotonic()
                    file_record = EmlJobFile(job_id=job_id, file_name=file_name, status="parsing")
                    db.add(file_record)
                    await db.flush()

                    try:
                        parsed = parse_eml_bytes(raw_bytes, file_name)

                        # Signature extraction
                        file_record.status = "signature"
                        await db.flush()
                        sig_data = extract_signature(
                            parsed.body_text, parsed.html_body,
                            parsed.from_name, parsed.from_email,
                        )

                        # AI enrichment placeholder
                        file_record.status = "ai"
                        await db.flush()
                        ai_result = await _call_ai_enrichment(sig_data, parsed.body_text, parsed.html_body)

                        # Finalize
                        method = _route_to_status(sig_data, ai_result)
                        file_record.status = "done"
                        file_record.extraction_method = method
                        file_record.confidence = sig_data.get("confidence", 0)
                        file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)

                        # Update job counters
                        job.processed += 1
                        job.succeeded += 1
                        if method.startswith("ai"):
                            job.ai_enriched += 1

                        contacts_batch.append(sig_data)

                    except Exception as e:
                        file_record.status = "failed"
                        file_record.error = str(e)[:2000]
                        file_record.attempts = 1
                        file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)
                        job.processed += 1
                        job.failed += 1
                        logger.warning("EML file %s failed: %s", file_name, e)

                    await db.flush()

                # Dedup within batch (informational — groups stored for future use)
                if contacts_batch:
                    deduplicate_contacts(contacts_batch)

            # Finalize job
            job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
            if job and job.status != "cancelled":
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()

        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)
            job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
            if job:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/eml/upload")
async def upload_eml_files(
    files: list[UploadFile] = File(...),
    job_name: str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """Upload .eml files, create a job, and start background processing."""
    valid_files: list[tuple[str, bytes]] = []
    errors: list[str] = []

    for f in files:
        if not f.filename or not f.filename.lower().endswith(".eml"):
            errors.append(f"Skipped non-EML file: {f.filename}")
            continue
        raw = await f.read()
        if len(raw) > 10 * 1024 * 1024:  # 10MB per file
            errors.append(f"Skipped {f.filename}: exceeds 10MB limit")
            continue
        valid_files.append((f.filename, raw))

    if not valid_files:
        raise HTTPException(400, detail={"error": "No valid .eml files provided", "errors": errors})

    job = EmlJob(
        job_name=job_name or f"EML batch {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        total_files=len(valid_files),
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(process_job_background, job.id, valid_files)

    return {
        "ok": True,
        "job_id": str(job.id),
        "total_files": len(valid_files),
        "errors": errors,
    }


@router.get("/eml/jobs")
async def list_jobs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List EML processing jobs, most recent first."""
    result = await db.execute(
        select(EmlJob).order_by(EmlJob.created_at.desc()).limit(limit)
    )
    jobs = result.scalars().all()
    return {
        "ok": True,
        "jobs": [
            {
                "id": str(j.id),
                "job_name": j.job_name,
                "status": j.status,
                "total_files": j.total_files,
                "processed": j.processed,
                "succeeded": j.succeeded,
                "failed": j.failed,
                "ai_enriched": j.ai_enriched,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ],
    }


@router.get("/eml/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get job detail with recent file records."""
    job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail="Job not found")

    files_result = await db.execute(
        select(EmlJobFile)
        .where(EmlJobFile.job_id == job_id)
        .order_by(EmlJobFile.created_at.desc())
        .limit(100)
    )
    files = files_result.scalars().all()

    return {
        "ok": True,
        "job": {
            "id": str(job.id),
            "job_name": job.job_name,
            "status": job.status,
            "total_files": job.total_files,
            "processed": job.processed,
            "succeeded": job.succeeded,
            "failed": job.failed,
            "ai_enriched": job.ai_enriched,
            "ocr_used": job.ocr_used,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "files": [
            {
                "id": str(f.id),
                "file_name": f.file_name,
                "status": f.status,
                "attempts": f.attempts,
                "error": f.error,
                "extraction_method": f.extraction_method,
                "confidence": f.confidence,
                "processing_time_ms": f.processing_time_ms,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in files
        ],
    }


@router.post("/eml/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running job."""
    job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail="Job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(400, detail=f"Job already {job.status}")

    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    return {"ok": True, "status": "cancelled"}
