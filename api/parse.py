from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import verify_token
from core.rate_limit import limiter
from services.parser import parse_xls, parse_pdf

router = APIRouter()

MAX_SIZE = 30 * 1024 * 1024  # 30 MB


@router.post("/parse")
@limiter.limit("30/minute")
async def parse_file(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "File is empty")
    if len(content) > MAX_SIZE:
        raise HTTPException(413, "File too large. Max 30 MB.")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()

    try:
        if ext in ("xls",):
            result = parse_xls(content)
        elif ext == "pdf":
            result = parse_pdf(content)
        elif ext == "xlsx":
            raise HTTPException(400, ".xlsx is handled in the browser — server accepts .xls and .pdf")
        else:
            raise HTTPException(400, f"Unsupported file type: .{ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, "Could not parse file")

    return JSONResponse(content={
        "ok": True,
        "sheet": result["sheet"],
        "headers": result["headers"],
        "rows": result["rows"],
        "rowCount": len(result["rows"]),
    })
