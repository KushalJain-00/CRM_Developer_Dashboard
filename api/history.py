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

@router.get("/history", dependencies=[Depends(verify_token)])
async def list_history(email: Optional[str] = Query(None), limit: int = 50, db: AsyncSession = Depends(get_db)):
    sessions = await list_sessions(db, email=email, limit=limit)
    return JSONResponse({"ok": True, "sessions": [
        {"id": s.id, "file_name": s.file_name, "sheet_name": s.sheet_name,
         "upload_date": s.upload_date.isoformat(), "total_records": s.total_records,
         "imported": s.imported, "skipped": s.skipped, "mapping": s.mapping}
        for s in sessions]})

@router.get("/history/{session_id}", dependencies=[Depends(verify_token)])
async def get_session_endpoint(session_id: int, page: int = 1, page_size: int = 100, db: AsyncSession = Depends(get_db)):
    s = await get_session(db, session_id)
    if not s: raise HTTPException(404, "Not found")
    total, records = await get_session_records(db, session_id, page, page_size)
    return JSONResponse({"ok": True, "file_name": s.file_name, "sheet_name": s.sheet_name,
        "mapping": s.mapping, "total": total, "records": [r.data for r in records]})

@router.delete("/history/{session_id}", dependencies=[Depends(verify_token)])
async def delete_session_endpoint(session_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await crud_delete_session(db, session_id)
    if not deleted: raise HTTPException(404, "Not found")
    return JSONResponse({"ok": True})

@router.get("/history/{session_id}/export", dependencies=[Depends(verify_token)])
async def export_session_with_calls(session_id: int, db: AsyncSession = Depends(get_db)):
    """Return all records + their call logs merged — for Excel re-export."""
    s = await get_session(db, session_id)
    if not s: raise HTTPException(404, "Not found")

    records = await get_all_session_records(db, session_id)

    # Pre-fetch contacts
    emails = []
    phones = []
    for r in records:
        row = dict(r.data or {})
        e = row.get('Email 1') or row.get('email') or row.get('Email') or row.get('email_primary')
        p = row.get('Mobile 1') or row.get('phone') or row.get('Phone') or row.get('phone_primary')
        if e: emails.append(e)
        if p: phones.append(p)

    contacts = []
    if emails:
        contacts.extend(await find_contacts_by_emails(db, emails))
    if phones:
        contacts.extend(await find_contacts_by_phones(db, phones))

    # Deduplicate contacts fetched from DB
    seen_ids = set()
    unique_contacts = []
    for c in contacts:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            unique_contacts.append(c)
    contacts = unique_contacts

    contact_by_email = {c.email_primary: c for c in contacts if c.email_primary}
    contact_by_phone = {c.phone_primary: c for c in contacts if c.phone_primary}

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
        
        contact = contact_by_email.get(email)
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