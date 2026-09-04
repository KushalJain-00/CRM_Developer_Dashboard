"""
Batch processing engine for EML pipeline.
Optimized for throughput: bulk inserts, checkpointing, resume support.
Reads files from disk staging dir — never holds all bytes in memory.
"""
import os
import json
import time
import logging
from pathlib import Path
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

CHECKPOINT_INTERVAL = 50
CONFIDENCE_THRESHOLD = 80  # Match eml_pipeline.py


async def _call_ai_enrichment(sig_data: dict, body_text: str, html_body: str) -> dict | None:
    """Call Groq LLM to validate/improve heuristic extraction."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
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

    try:
        raw = await call_llm("groq", "llama-3.3-70b-versatile", api_key, SYSTEM_PROMPT, prompt)
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            return parsed[0]
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.debug("AI enrichment failed: %s", e)
    return None


def _merge_ai_into_sig(sig_data: dict, ai_result: dict | None) -> dict:
    """Merge AI results into heuristic data. AI fills gaps, heuristic wins on conflicts."""
    if not ai_result:
        return sig_data
    merged = dict(sig_data)
    for key in ["name", "company", "designation", "phone_primary", "phone_secondary",
                "email", "website", "address", "city", "pincode"]:
        if not merged.get(key) and ai_result.get(key):
            merged[key] = ai_result[key]
    return merged


async def process_job_optimized(job_id: UUID, staging_dir: str):
    """Optimized batch processor with checkpointing and resume support.

    - Reads files from disk staging dir (no memory hold)
    - Skips already-processed files on resume
    - Batches EmlJobFile inserts
    - Commits at CHECKPOINT_INTERVAL boundaries
    - AI enrichment only when heuristic confidence < 80
    """
    staging = Path(staging_dir)
    if not staging.exists():
        logger.error("Staging dir %s not found for job %s", staging_dir, job_id)
        return

    async with AsyncSessionLocal() as db:
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

        all_files = sorted(staging.glob("*.eml"))
        remaining = [fp for fp in all_files if fp.name not in processed_names]

        if processed_names:
            logger.info(
                "Resuming job %s: %d already processed, %d remaining",
                job_id, len(processed_names), len(remaining),
            )

        file_records_pending: list[EmlJobFile] = []

        try:
            for i, fp in enumerate(remaining):
                job = (await db.execute(
                    select(EmlJob).where(EmlJob.id == job_id)
                )).scalar_one_or_none()
                if not job or job.status == "cancelled":
                    if file_records_pending:
                        db.add_all(file_records_pending)
                        await db.commit()
                    return

                t0 = time.monotonic()
                file_record = EmlJobFile(
                    job_id=job_id, file_name=fp.name, status="parsing"
                )

                try:
                    raw_bytes = fp.read_bytes()
                    parsed = parse_eml_bytes(raw_bytes, fp.name)
                    sig_data = extract_signature(
                        parsed.body_text, parsed.html_body,
                        parsed.from_name, parsed.from_email,
                    )

                    # AI enrichment — only when heuristic confidence is low
                    confidence = sig_data.get("confidence", 0)
                    ai_result = None
                    if confidence < CONFIDENCE_THRESHOLD:
                        ai_result = await _call_ai_enrichment(sig_data, parsed.body_text, parsed.html_body)
                        sig_data = _merge_ai_into_sig(sig_data, ai_result)

                    method = "ai_extract" if ai_result else ("deterministic" if confidence >= CONFIDENCE_THRESHOLD else "heuristic")

                    file_record.status = "done"
                    file_record.extraction_method = method
                    file_record.confidence = sig_data.get("confidence", 0)
                    file_record.extracted_data = sig_data
                    file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)
                    file_record.attempts = 1

                    job.succeeded += 1
                    if method == "ai_extract":
                        job.ai_enriched += 1

                except Exception as e:
                    file_record.status = "failed"
                    file_record.error = str(e)[:2000]
                    file_record.attempts = 1
                    file_record.processing_time_ms = int((time.monotonic() - t0) * 1000)
                    job.failed += 1
                    logger.warning("EML file %s failed: %s", fp.name, e)

                job.processed += 1
                file_records_pending.append(file_record)

                if len(file_records_pending) >= CHECKPOINT_INTERVAL:
                    db.add_all(file_records_pending)
                    await db.commit()
                    file_records_pending = []
                    logger.info("Job %s: %d/%d processed", job_id, i + 1, len(remaining))

            if file_records_pending:
                db.add_all(file_records_pending)
                await db.commit()

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
