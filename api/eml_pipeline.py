"""EML Pipeline API — upload, process, and track .eml file batches."""
import os
import json
import time
import logging
import tempfile
import shutil
from pathlib import Path
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
from services.eml_retry import get_dead_letter_queue, delete_dead_letter, MAX_RETRIES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eml-pipeline"])

CONFIDENCE_THRESHOLD = 80  # heuristic >= this → skip AI
STAGING_DIR = Path(tempfile.gettempdir()) / "eml_uploads"


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AI enrichment
# ---------------------------------------------------------------------------

async def _call_ai_enrichment(sig_data: dict, body_text: str, html_body: str, ai_chain: list | None) -> dict | None:
    """Call client's LLM provider chain to validate/improve heuristic extraction.

    Uses the same provider chain the user configured in AI Settings.
    Falls back through the chain if a provider fails.
    """
    if not ai_chain:
        return None

    from api.parse_signature import call_llm, clean_email_text, SYSTEM_PROMPT

    existing = {k: v for k, v in sig_data.items() if v and k != "confidence"}
    text = clean_email_text(body_text) or clean_email_text(html_body) or ""
    if not text or len(text) < 10:
        return None

    prompt = (
        f"Extract and VALIDATE contact info from this email.\n"
        f"We already extracted (verify/correct):\n{json.dumps(existing, indent=2)}\n\n"
        f"Email text:\n{text[:2500]}"
    )

    for attempt in ai_chain:
        api_key = attempt.get("api_key", "") if isinstance(attempt, dict) else getattr(attempt, "api_key", "")
        provider = attempt.get("provider", "") if isinstance(attempt, dict) else getattr(attempt, "provider", "")
        model = attempt.get("model", "") if isinstance(attempt, dict) else getattr(attempt, "model", "")
        if not api_key or not provider or not model:
            continue
        try:
            raw = await call_llm(provider, model, api_key, SYSTEM_PROMPT, prompt)
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return parsed[0]
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logger.debug("AI enrichment failed (%s/%s): %s", provider, model, e)
    return None


def _merge_ai_into_sig(sig_data: dict, ai_result: dict | None) -> dict:
    """Merge AI results into heuristic data. AI fills gaps, heuristic wins on conflicts."""
    if not ai_result:
        return sig_data
    merged = dict(sig_data)
    for key in ["name", "company", "designation", "phone_primary", "phone_secondary",
                "email", "website", "address", "city", "pincode"]:
        existing = merged.get(key)
        ai_val = ai_result.get(key)
        # AI fills empty fields; if both exist and differ, prefer heuristic (deterministic)
        if not existing and ai_val:
            merged[key] = ai_val
    return merged


def _route_to_status(sig_data: dict, ai_result: dict | None) -> str:
    """Determine extraction_method from results."""
    if ai_result:
        return "ai_extract"
    confidence = sig_data.get("confidence", 0)
    if confidence >= CONFIDENCE_THRESHOLD:
        return "deterministic"
    return "heuristic"


async def process_job_background(job_id: UUID, staging_dir: str):
    """Process all files in a job. Reads from disk staging dir, not memory."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(EmlJob).where(EmlJob.id == job_id).values(status="processing")
        )
        await db.commit()

        # Load client's AI chain from job
        job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
        ai_chain = job.ai_chain if job else None

        staging = Path(staging_dir)
        if not staging.exists():
            logger.error("Staging dir %s not found for job %s", staging_dir, job_id)
            return

        file_paths = sorted(staging.glob("*.eml"))
        batch_size = 50
        try:
            for batch_start in range(0, len(file_paths), batch_size):
                batch = file_paths[batch_start:batch_start + batch_size]

                job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
                if not job or job.status == "cancelled":
                    return

                contacts_batch = []

                for fp in batch:
                    t0 = time.monotonic()
                    file_record = EmlJobFile(job_id=job_id, file_name=fp.name, status="parsing")
                    db.add(file_record)
                    await db.flush()

                    try:
                        raw_bytes = fp.read_bytes()
                        parsed = parse_eml_bytes(raw_bytes, fp.name)

                        # Heuristic signature extraction
                        file_record.status = "signature"
                        await db.flush()
                        sig_data = extract_signature(
                            parsed.body_text, parsed.html_body,
                            parsed.from_name, parsed.from_email,
                        )

                        # AI enrichment — only when heuristic confidence is low
                        confidence = sig_data.get("confidence", 0)
                        ai_result = None
                        if confidence < CONFIDENCE_THRESHOLD:
                            file_record.status = "ai"
                            await db.flush()
                            ai_result = await _call_ai_enrichment(sig_data, parsed.body_text, parsed.html_body, ai_chain)
                            sig_data = _merge_ai_into_sig(sig_data, ai_result)

                        # Finalize
                        method = _route_to_status(sig_data, ai_result)
                        file_record.status = "done"
                        file_record.extraction_method = method
                        file_record.confidence = sig_data.get("confidence", 0)
                        file_record.extracted_data = sig_data
                        file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)

                        job.processed += 1
                        job.succeeded += 1
                        if method == "ai_extract":
                            job.ai_enriched += 1

                        contacts_batch.append(sig_data)

                    except Exception as e:
                        file_record.status = "failed"
                        file_record.error = str(e)[:2000]
                        file_record.attempts = 1
                        file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)
                        job.processed += 1
                        job.failed += 1
                        logger.warning("EML file %s failed: %s", fp.name, e)

                    await db.flush()

                if contacts_batch:
                    deduplicate_contacts(contacts_batch)

            # Finalize
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
        finally:
            # Cleanup staging dir after processing
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/eml/upload")
async def upload_eml_files(
    files: list[UploadFile] = File(...),
    job_name: str = Form(""),
    ai_chain: str = Form("[]"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """Upload .eml files, create a job, and start background processing."""
    # Parse client's AI chain from JSON string
    try:
        chain_data = json.loads(ai_chain) if ai_chain else []
    except json.JSONDecodeError:
        chain_data = []

    job_id = UUID(bytes=os.urandom(16))
    staging = STAGING_DIR / str(job_id)
    staging.mkdir(parents=True, exist_ok=True)

    saved = 0
    errors: list[str] = []

    for f in files:
        if not f.filename or not f.filename.lower().endswith(".eml"):
            errors.append(f"Skipped non-EML file: {f.filename}")
            continue
        raw = await f.read()
        if len(raw) > 10 * 1024 * 1024:
            errors.append(f"Skipped {f.filename}: exceeds 10MB limit")
            continue
        (staging / f.filename).write_bytes(raw)
        saved += 1

    if not saved:
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(400, detail={"error": "No valid .eml files provided", "errors": errors})

    job = EmlJob(
        id=job_id,
        job_name=job_name or f"EML batch {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        total_files=saved,
        status="pending",
        ai_chain=chain_data if chain_data else None,
    )
    db.add(job)
    await db.commit()

    background_tasks.add_task(process_job_background, job_id, str(staging))

    return {
        "ok": True,
        "job_id": str(job_id),
        "total_files": saved,
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


@router.post("/eml/jobs/{job_id}/retry")
async def retry_job_files(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Retry all failed files in a job. Requires staging dir to still exist."""
    job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail="Job not found")

    staging = STAGING_DIR / str(job_id)
    if not staging.exists():
        raise HTTPException(400, detail="Staging files cleaned up. Re-upload to retry.")

    # Mark failed files as pending for re-processing
    await db.execute(
        update(EmlJobFile).where(
            EmlJobFile.job_id == job_id,
            EmlJobFile.status == "failed",
            EmlJobFile.attempts < MAX_RETRIES,
        ).values(status="retrying")
    )
    await db.commit()

    background_tasks.add_task(process_job_background, job_id, str(staging))
    return {"ok": True, "message": "Retry started in background"}


@router.get("/eml/jobs/{job_id}/dead-letter")
async def get_dead_letter(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get files that have exhausted all retry attempts."""
    job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail="Job not found")

    files = await get_dead_letter_queue(job_id, db)
    return {
        "ok": True,
        "files": [
            {
                "id": str(f.id),
                "file_name": f.file_name,
                "attempts": f.attempts,
                "error": f.error,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            }
            for f in files
        ],
    }


@router.post("/eml/jobs/{job_id}/dead-letter/abandon")
async def abandon_dead_letter(
    job_id: UUID,
    file_ids: list[UUID] = [],
    db: AsyncSession = Depends(get_db),
):
    """Mark dead letter files as abandoned (give up on them)."""
    if not file_ids:
        raise HTTPException(400, detail="No file IDs provided")

    job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, detail="Job not found")

    result = await delete_dead_letter(job_id, file_ids, db)
    return {"ok": True, **result}
