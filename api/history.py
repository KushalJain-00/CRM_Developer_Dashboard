from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from typing import Optional, List
from db.database import get_db
from db.models import SessionData, Record, User, Contact, CallLog

router = APIRouter()


# ── Session queries ───────────────────────────────────────────────────

async def _list_sessions(db: AsyncSession, email: Optional[str] = None, limit: int = 50):
    q = select(SessionData)
    if email:
        result = await db.execute(select(User).filter(User.email == email))
        u = result.scalars().first()
        if u:
            q = q.filter(or_(SessionData.user_id == u.id, SessionData.user_id.is_(None)))
    q = q.order_by(SessionData.upload_date.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def _get_session(db: AsyncSession, session_id: int):
    result = await db.execute(select(SessionData).filter(SessionData.id == session_id))
    return result.scalars().first()


async def _get_session_records(db: AsyncSession, session_id: int, page: int = 1, page_size: int = 100):
    count_result = await db.execute(
        select(func.count()).select_from(Record).filter(Record.session_id == session_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Record).filter(Record.session_id == session_id)
        .offset((page - 1) * page_size).limit(page_size)
    )
    return total, result.scalars().all()


async def _delete_session(db: AsyncSession, session_id: int) -> bool:
    result = await db.execute(select(SessionData).filter(SessionData.id == session_id))
    s = result.scalars().first()
    if not s:
        return False
    await db.delete(s)
    await db.commit()
    return True


async def _get_all_session_records(db: AsyncSession, session_id: int) -> List[Record]:
    result = await db.execute(
        select(Record).filter(Record.session_id == session_id)
    )
    return result.scalars().all()


async def _find_contacts_by_emails(db: AsyncSession, emails: List[str]) -> List[Contact]:
    contacts = []
    for i in range(0, len(emails), 2000):
        chunk = [e.lower() for e in emails[i:i + 2000]]
        # ponytail: lower() both sides — records carry mixed-case emails, DB may too
        result = await db.execute(select(Contact).filter(func.lower(Contact.email_primary).in_(chunk)))
        contacts.extend(result.scalars().all())
    return contacts


async def _find_contacts_by_phones(db: AsyncSession, phones: List[str]) -> List[Contact]:
    contacts = []
    for i in range(0, len(phones), 2000):
        chunk = phones[i:i + 2000]
        result = await db.execute(select(Contact).filter(Contact.phone_primary.in_(chunk)))
        contacts.extend(result.scalars().all())
    return contacts


async def _get_call_logs_for_contacts(db: AsyncSession, contact_ids: List[int]) -> dict:
    logs_by_contact = {}
    for i in range(0, len(contact_ids), 2000):
        chunk = contact_ids[i:i + 2000]
        result = await db.execute(
            select(CallLog).filter(CallLog.contact_id.in_(chunk)).order_by(CallLog.call_date.desc())
        )
        for log in result.scalars().all():
            logs_by_contact.setdefault(log.contact_id, []).append(log)
    return logs_by_contact


async def _rows_with_contact(db: AsyncSession, records):
    """Yield (row_dict, contact|None) per record — contact resolved via email/phone.

    Shared by get_session_endpoint and export_session_with_calls.
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
        fetched.extend(await _find_contacts_by_emails(db, emails))
    if phones:
        fetched.extend(await _find_contacts_by_phones(db, phones))
    contacts = list({c.id: c for c in fetched}.values())
    by_email = {c.email_primary.lower(): c for c in contacts if c.email_primary}
    by_phone = {c.phone_primary: c for c in contacts if c.phone_primary}

    out = []
    for r in records:
        row = dict(r.data or {})
        e = row.get('Email 1') or row.get('email') or row.get('Email') or row.get('email_primary')
        p = row.get('Mobile 1') or row.get('phone') or row.get('Phone') or row.get('phone_primary')
        contact = by_email.get(e.lower()) if e else None
        if not contact and p:
            contact = by_phone.get(p)
        out.append((row, contact))
    return out


# ── Routes ────────────────────────────────────────────────────────────

@router.get("/history")
async def list_history(email: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    sessions = await _list_sessions(db, email=email, limit=limit)
    return JSONResponse({"ok": True, "sessions": [
        {"id": s.id, "file_name": s.file_name, "sheet_name": s.sheet_name,
         "upload_date": s.upload_date.isoformat(), "total_records": s.total_records,
         "imported": s.imported, "skipped": s.skipped, "mapping": s.mapping}
        for s in sessions]})

@router.get("/history/{session_id}")
async def get_session_endpoint(session_id: int, page: int = 1, page_size: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    s = await _get_session(db, session_id)
    if not s: raise HTTPException(404, "Not found")
    total, records = await _get_session_records(db, session_id, page, page_size)

    out_records = []
    for row, contact in await _rows_with_contact(db, records):
        if contact:
            row['_contact_id'] = contact.id
        out_records.append(row)

    return JSONResponse({"ok": True, "file_name": s.file_name, "sheet_name": s.sheet_name,
        "mapping": s.mapping, "total": total, "records": out_records})

@router.delete("/history/{session_id}")
async def delete_session_endpoint(session_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await _delete_session(db, session_id)
    if not deleted: raise HTTPException(404, "Not found")
    return JSONResponse({"ok": True})

@router.get("/history/{session_id}/export")
async def export_session_with_calls(session_id: int, db: AsyncSession = Depends(get_db)):
    """Return all records + their call logs merged — for Excel re-export."""
    s = await _get_session(db, session_id)
    if not s: raise HTTPException(404, "Not found")

    records = await _get_all_session_records(db, session_id)
    matched = await _rows_with_contact(db, records)

    # Pre-fetch call logs for matched contacts
    contact_ids = [c.id for _, c in matched if c]
    logs_by_contact = await _get_call_logs_for_contacts(db, contact_ids) if contact_ids else {}

    # For each record, attach call logs if its contact has any
    result = []
    for row, contact in matched:
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
