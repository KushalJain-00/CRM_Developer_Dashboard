"""Monitoring and analytics API for EML pipeline."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.database import get_db
from db.eml_models import EmlJob, EmlJobFile

router = APIRouter(tags=["eml-monitor"])


@router.get("/eml/stats")
async def get_pipeline_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count(EmlJob.id)))
    total_jobs = result.scalar() or 0

    result = await db.execute(
        select(EmlJob.status, func.count(EmlJob.id)).group_by(EmlJob.status)
    )
    status_counts = {row[0]: row[1] for row in result.fetchall()}

    result = await db.execute(select(func.coalesce(func.sum(EmlJob.total_files), 0)))
    total_files = result.scalar()

    result = await db.execute(select(func.coalesce(func.sum(EmlJob.processed), 0)))
    total_processed = result.scalar()

    result = await db.execute(select(func.coalesce(func.sum(EmlJob.succeeded), 0)))
    total_succeeded = result.scalar()

    result = await db.execute(select(func.coalesce(func.sum(EmlJob.failed), 0)))
    total_failed = result.scalar()

    result = await db.execute(select(func.coalesce(func.sum(EmlJob.ai_enriched), 0)))
    total_ai = result.scalar()

    result = await db.execute(
        select(func.avg(EmlJobFile.confidence)).where(EmlJobFile.status == "done")
    )
    avg_confidence = round(result.scalar() or 0, 1)

    result = await db.execute(
        select(EmlJobFile.extraction_method, func.count(EmlJobFile.id))
        .where(EmlJobFile.status == "done")
        .group_by(EmlJobFile.extraction_method)
    )
    method_counts = {row[0] or "unknown": row[1] for row in result.fetchall()}

    return {
        "ok": True,
        "stats": {
            "total_jobs": total_jobs,
            "jobs_by_status": status_counts,
            "total_files": total_files,
            "total_processed": total_processed,
            "total_succeeded": total_succeeded,
            "total_failed": total_failed,
            "total_ai_enriched": total_ai,
            "avg_confidence": avg_confidence,
            "method_breakdown": method_counts,
            "estimated_ai_cost_usd": round(total_ai * 0.001, 3),
        },
    }


@router.get("/eml/stats/throughput")
async def get_throughput(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.min(EmlJobFile.processing_time_ms),
            func.max(EmlJobFile.processing_time_ms),
            func.avg(EmlJobFile.processing_time_ms),
        ).where(EmlJobFile.status == "done")
    )
    row = result.fetchone()
    min_time = row[0] or 0
    max_time = row[1] or 0
    avg_time = round(row[2] or 0, 1)
    files_per_hour = int(3600000 / avg_time) if avg_time > 0 else 0

    return {
        "ok": True,
        "throughput": {
            "avg_processing_time_ms": avg_time,
            "min_processing_time_ms": min_time,
            "max_processing_time_ms": max_time,
            "estimated_files_per_hour": files_per_hour,
        },
    }


@router.get("/eml/stats/errors")
async def get_error_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EmlJobFile.error, func.count(EmlJobFile.id))
        .where(EmlJobFile.status == "failed", EmlJobFile.error.isnot(None))
        .group_by(EmlJobFile.error)
        .order_by(func.count(EmlJobFile.id).desc())
        .limit(10)
    )
    top_errors = [{"error": row[0], "count": row[1]} for row in result.fetchall()]

    result = await db.execute(
        select(func.avg(EmlJobFile.attempts)).where(EmlJobFile.status == "done")
    )
    avg_attempts = round(result.scalar() or 1, 2)

    return {
        "ok": True,
        "errors": {
            "top_errors": top_errors,
            "avg_attempts_on_success": avg_attempts,
        },
    }
