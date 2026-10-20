from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from core.auth import verify_token
from db.database import get_db
from crud.history import (
    list_sessions, get_session, get_session_records,
    delete_session as crud_delete_session,
    get_all_session_records, find_contacts_by_emails,
    find_contacts_by_phones, get_call_logs_for_contacts
)

router = APIRouter()

async def _match_records_to_contacts(db: AsyncSession, records):
    """Fetch contacts referenced by records' email/phone.

    Shared by get_session_endpoint and export_session_with_calls.
    Returns (unique contacts, by_email map, by_phone map).
    """
    emails = []
    phones = []
    for r in records:
        row = r.data or {}
        e = row.get('Email 1') or row.get('email') or row.get('Email') or row.get('email_primary')
        p = row.get('Mobile 1') or row.get('phone') or row.get('Phone') or row.get('phone_primary')
        if e: emails.append(e)
        if p: phones.append(p)

    fetched = []
    if emails:
        fetched.extend(await find_contacts_by_emails(db, emails))
    if phones:
        fetched.extend(await find_contacts_by_phones(db, phones))
    contacts = list({c.id: c for c in fetched}.values())
    by_email = {c.email_primary.lower(): c for c in contacts if c.email_primary}
    by_phone = {c.phone_primary: c for c in contacts if c.phone_primary}
    return contacts, by_email, by_phone

@router.get("/history")
async def list_history(email: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    sessions = await list_sessions(db, email=email, limit=limit)
    return JSONResponse({"ok": True, "sessions": [
        {"id": s.id, "file_name": s.file_name, "sheet_name": s.sheet_name,
         "upload_date": s.upload_date.isoformat(), "total_records": s.total_records,
         "imported": s.imported, "skipped": s.skipped, "mapping": s.mapping}
        for s in sessions]})

@router.get("/history/{session_id}")
async def get_session_endpoint(session_id: int, page: int = 1, page_size: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    s = await get_session(db, session_id)
    if not s: raise HTTPException(404, "Not found")
    total, records = await get_session_records(db, session_id, page, page_size)
    
    # Pre-fetch contacts to attach IDs for frontend editing
    _, c_by_email, c_by_phone = await _match_records_to_contacts(db, records)

    out_records = []
    for r in records:
        row = dict(r.data or {})
        e = row.get('Email 1') or row.get('email') or row.get('Email') or row.get('email_primary')
        p = row.get('Mobile 1') or row.get('phone') or row.get('Phone') or row.get('phone_primary')
        
        contact = c_by_email.get(e.lower()) if e else None
        if not contact and p:
            contact = c_by_phone.get(p)
            
        if contact:
            row['_contact_id'] = contact.id
            
        out_records.append(row)

    return JSONResponse({"ok": True, "file_name": s.file_name, "sheet_name": s.sheet_name,
        "mapping": s.mapping, "total": total, "records": out_records})

@router.delete("/history/{session_id}")
async def delete_session_endpoint(session_id: int, db: AsyncSession = Depends(get_db), current_user = Depends(verify_token)):
    deleted = await crud_delete_session(db, session_id)
    if not deleted: raise HTTPException(404, "Not found")
    return JSONResponse({"ok": True})

@router.get("/history/{session_id}/export")
async def export_session_with_calls(session_id: int, db: AsyncSession = Depends(get_db)):
    """Return all records + their call logs merged — for Excel re-export."""
    s = await get_session(db, session_id)
    if not s: raise HTTPException(404, "Not found")

    records = await get_all_session_records(db, session_id)

    # Pre-fetch contacts + lookup maps (shared helper)
    contacts, contact_by_email, contact_by_phone = await _match_records_to_contacts(db, records)

    # Pre-fetch call logs
    contact_ids = [c.id for c in contacts]
    logs_by_contact = {}
    if contact_ids:
        logs_by_contact = await get_call_logs_for_contacts(db, contact_ids)

    # For each record, try to find its contact and attach call logs
    result = []
    for r in records:
        row = dict(r.data or {})
        email = row.get('Email 1') or row.get('email') or row.get('Email') or row.get('email_primary')
        phone = row.get('Mobile 1') or row.get('phone') or row.get('Phone') or row.get('phone_primary')
        
        contact = contact_by_email.get(email.lower() if email else None)
        if not contact and phone:
            contact = contact_by_phone.get(phone)

        if contact:
            logs = logs_by_contact.get(contact.id, [])
            if logs:
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