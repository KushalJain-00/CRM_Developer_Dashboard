from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from core.auth import verify_api_key
from db.database import get_db
from db.models import SessionData, Record, User, Contact, CallLog, Company

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

@router.get("/history/{session_id}/export", dependencies=[Depends(verify_api_key)])
async def export_session_with_calls(session_id: int, db: Session = Depends(get_db)):
    """Return all records + their call logs merged — for Excel re-export."""
    s = db.query(SessionData).filter(SessionData.id == session_id).first()
    if not s: raise HTTPException(404, "Not found")

    records = db.query(Record).filter(Record.session_id == session_id).all()

    # For each record, try to find its contact and attach call logs
    result = []
    for r in records:
        row = dict(r.data or {})
        # Match contact by email or phone
        email = row.get('email') or row.get('Email') or row.get('email_primary')
        phone = row.get('phone') or row.get('Phone') or row.get('phone_primary')
        contact = None
        if email:
            contact = db.query(Contact).filter(Contact.email_primary == email).first()
        if not contact and phone:
            contact = db.query(Contact).filter(Contact.phone_primary == phone).first()

        if contact:
            logs = db.query(CallLog).filter(CallLog.contact_id == contact.id)\
                     .order_by(CallLog.call_date.desc()).all()
            if logs:
                # Flatten call logs into columns: Last Call Date, Last Outcome, All Notes
                row['_last_call_date']    = logs[0].call_date.strftime('%Y-%m-%d %H:%M') if logs[0].call_date else ''
                row['_last_call_type']    = logs[0].call_type or ''
                row['_last_outcome']      = logs[0].outcome or ''
                row['_last_notes']        = logs[0].notes or ''
                row['_total_calls']       = len(logs)
                row['_next_action']       = logs[0].next_action or ''
                row['_next_action_date']  = logs[0].next_action_date.strftime('%Y-%m-%d') if logs[0].next_action_date else ''
                row['_all_call_summary']  = ' | '.join(
                    f"{l.call_date.strftime('%d/%m/%y')} {l.call_type} → {l.outcome}: {(l.notes or '')[:60]}"
                    for l in logs
                )
        result.append(row)

    return JSONResponse({
        "ok": True,
        "file_name": s.file_name,
        "sheet_name": s.sheet_name,
        "mapping": s.mapping,
        "records": result
    })