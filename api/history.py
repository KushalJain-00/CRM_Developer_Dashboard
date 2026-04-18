from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from core.auth import verify_api_key
from db.database import get_db
from db.models import SessionData, Record, User

router = APIRouter()

@router.get("/history", dependencies=[Depends(verify_api_key)])
async def list_history(email: Optional[str] = Query(None), limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(SessionData)
    if email:
        u = db.query(User).filter(User.email == email).first()
        if u: q = q.filter(SessionData.user_id == u.id)
    sessions = q.order_by(SessionData.upload_date.desc()).limit(limit).all()
    return JSONResponse({"ok": True, "sessions": [
        {"id": s.id, "file_name": s.file_name, "sheet_name": s.sheet_name,
         "upload_date": s.upload_date.isoformat(), "total_records": s.total_records,
         "imported": s.imported, "skipped": s.skipped, "mapping": s.mapping}
        for s in sessions]})

@router.get("/history/{session_id}", dependencies=[Depends(verify_api_key)])
async def get_session(session_id: int, page: int = 1, page_size: int = 100, db: Session = Depends(get_db)):
    s = db.query(SessionData).filter(SessionData.id == session_id).first()
    if not s: raise HTTPException(404, "Not found")
    total = db.query(Record).filter(Record.session_id == session_id).count()
    records = db.query(Record).filter(Record.session_id == session_id)\
        .offset((page-1)*page_size).limit(page_size).all()
    return JSONResponse({"ok": True, "file_name": s.file_name, "sheet_name": s.sheet_name,
        "mapping": s.mapping, "total": total, "records": [r.data for r in records]})

@router.delete("/history/{session_id}", dependencies=[Depends(verify_api_key)])
async def delete_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(SessionData).filter(SessionData.id == session_id).first()
    if not s: raise HTTPException(404, "Not found")
    db.delete(s); db.commit()
    return JSONResponse({"ok": True})