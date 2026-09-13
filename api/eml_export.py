"""Export API endpoints for EML pipeline results."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from db.database import get_db
from db.eml_models import EmlJob, EmlJobFile
from services.eml_export import export_csv, export_vcf, export_excel_data

router = APIRouter(tags=["eml-export"])


async def _get_job_files(db: AsyncSession, job_id: UUID):
    """Fetch job and its completed files. Raises 404 if job missing."""
    job = (await db.execute(select(EmlJob).where(EmlJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    result = await db.execute(
        select(EmlJobFile).where(
            EmlJobFile.job_id == job_id,
            EmlJobFile.status == "done",
        )
    )
    return job, result.scalars().all()


def _files_to_contacts(files) -> list[dict]:
    """Convert EmlJobFile records to contact dicts using persisted extracted_data."""
    contacts = []
    for f in files:
        data = f.extracted_data if isinstance(f.extracted_data, dict) else (json.loads(f.extracted_data) if f.extracted_data else {})
        data["extraction_method"] = f.extraction_method or ""
        data["confidence"] = f.confidence or 0
        contacts.append(data)
    return contacts


@router.get("/eml/jobs/{job_id}/export/csv")
async def export_job_csv(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """Export job results as CSV."""
    _, files = await _get_job_files(db, job_id)
    contacts = _files_to_contacts(files)
    csv_content = export_csv(contacts)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=eml_export_{job_id}.csv"},
    )


@router.get("/eml/jobs/{job_id}/export/vcf")
async def export_job_vcf(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """Export job results as VCF."""
    _, files = await _get_job_files(db, job_id)
    contacts = _files_to_contacts(files)
    vcf_content = export_vcf(contacts)
    return Response(
        content=vcf_content,
        media_type="text/vcard",
        headers={"Content-Disposition": f"attachment; filename=eml_export_{job_id}.vcf"},
    )


@router.get("/eml/jobs/{job_id}/export/excel")
async def export_job_excel(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """Export job results as Excel (JSON data for client-side XLSX generation)."""
    _, files = await _get_job_files(db, job_id)
    contacts = _files_to_contacts(files)
    data = export_excel_data(contacts)
    return {"ok": True, "data": data}
