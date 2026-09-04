"""Server-Sent Events for real-time EML pipeline progress."""
import asyncio
import json
import logging
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from db.database import AsyncSessionLocal
from db.eml_models import EmlJob, EmlJobFile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eml-sse"])


async def _event_stream(job_id: UUID):
    last_processed = 0
    async with AsyncSessionLocal() as db:
        while True:
            result = await db.execute(select(EmlJob).where(EmlJob.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                return

            event_data = {
                "type": "progress",
                "job_id": str(job.id),
                "status": job.status,
                "total_files": job.total_files,
                "processed": job.processed,
                "succeeded": job.succeeded,
                "failed": job.failed,
                "ai_enriched": job.ai_enriched,
                "percent": round((job.processed / job.total_files * 100) if job.total_files > 0 else 0, 1),
                "timestamp": datetime.now().isoformat(),
            }

            if job.processed > last_processed:
                files_result = await db.execute(
                    select(EmlJobFile)
                    .where(EmlJobFile.job_id == job_id)
                    .order_by(EmlJobFile.updated_at.desc())
                    .limit(10)
                )
                recent_files = files_result.scalars().all()
                event_data["recent_files"] = [
                    {"file_name": f.file_name, "status": f.status, "confidence": f.confidence, "extraction_method": f.extraction_method}
                    for f in recent_files
                ]
                last_processed = job.processed

            yield f"data: {json.dumps(event_data)}\n\n"

            if job.status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'type': 'done', 'status': job.status})}\n\n"
                return

            await asyncio.sleep(1)


@router.get("/eml/jobs/{job_id}/stream")
async def stream_job_progress(job_id: UUID):
    return StreamingResponse(
        _event_stream(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
