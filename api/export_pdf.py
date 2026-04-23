from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import verify_api_key
from services.pdf_exporter import generate_pdf
from pydantic import BaseModel
from typing import Any, Optional

router = APIRouter()


class PDFRequest(BaseModel):
    fileName: str
    sheetName: str
    total: int
    fields: int
    completeness: int
    withEmail: Optional[int] = None
    withPhone: Optional[int] = None
    fieldQuality: list[dict]
    records: list[dict]
    columns: list[str]


@router.post("/export/pdf", dependencies=[Depends(verify_api_key)])
async def export_pdf(body: PDFRequest):
    try:
        pdf_bytes = generate_pdf(body.model_dump())
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {str(e)}")

    # Sanitize filename to prevent header injection
    import re
    safe_name = re.sub(r'[^\w\s\-\.]', '', body.fileName or 'export').strip() or 'export'

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_CRM_Report.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        }
    )
