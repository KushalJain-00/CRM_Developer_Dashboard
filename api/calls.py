"""
Call Logs API — Tracks all call discussions linked to contacts.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from core.auth import verify_token
from db.database import get_db
from db.models import CallLog, Contact, Company

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────

class CallLogIn(BaseModel):
    contact_id: int
    company_id: Optional[int] = None
    call_date: Optional[str] = None       # ISO date string
    duration_minutes: Optional[int] = None
    call_type: str = "Outgoing"           # Incoming, Outgoing, Follow-up
    outcome: str = "Connected"            # Connected, No Answer, Voicemail, Callback Scheduled
    notes: str = ""
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    created_by: Optional[str] = None


class CallLogUpdate(BaseModel):
    call_type: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    duration_minutes: Optional[int] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None


def _log_to_dict(log: CallLog) -> dict:
    return {
        "id": log.id,
        "contact_id": log.contact_id,
        "company_id": log.company_id,
        "call_date": log.call_date.isoformat() if log.call_date else None,
        "duration_minutes": log.duration_minutes,
        "call_type": log.call_type,
        "outcome": log.outcome,
        "notes": log.notes,
        "next_action": log.next_action,
        "next_action_date": log.next_action_date.isoformat() if log.next_action_date else None,
        "created_by": log.created_by,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────

@router.post("/calls", dependencies=[Depends(verify_token)])
async def create_call_log(body: CallLogIn, db: AsyncSession = Depends(get_db)):
    """Record a new call discussion for a contact."""
    # Verify contact exists
    result = await db.execute(select(Contact).filter(Contact.id == body.contact_id))
    contact = result.scalars().first()
    if not contact:
        raise HTTPException(404, "Contact not found")

    call_date = datetime.fromisoformat(body.call_date) if body.call_date else datetime.utcnow()
    next_date = datetime.fromisoformat(body.next_action_date) if body.next_action_date else None

    log = CallLog(
        contact_id=body.contact_id,
        company_id=body.company_id or contact.company_id,
        call_date=call_date,
        duration_minutes=body.duration_minutes,
        call_type=body.call_type,
        outcome=body.outcome,
        notes=body.notes,
        next_action=body.next_action,
        next_action_date=next_date,
        created_by=body.created_by,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return JSONResponse(content={"ok": True, "call_log": _log_to_dict(log)})


@router.get("/calls/contact/{contact_id}", dependencies=[Depends(verify_token)])
async def get_call_logs_for_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all call logs for a specific contact, newest first."""
    result = await db.execute(
        select(CallLog).filter(CallLog.contact_id == contact_id)
        .order_by(CallLog.call_date.desc())
    )
    logs = result.scalars().all()

    return JSONResponse(content={
        "ok": True,
        "contact_id": contact_id,
        "logs": [_log_to_dict(l) for l in logs],
    })


@router.put("/calls/{log_id}", dependencies=[Depends(verify_token)])
async def update_call_log(log_id: int, body: CallLogUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallLog).filter(CallLog.id == log_id))
    log = result.scalars().first()
    if not log:
        raise HTTPException(404, "Call log not found")

    if body.call_type is not None:
        log.call_type = body.call_type
    if body.outcome is not None:
        log.outcome = body.outcome
    if body.notes is not None:
        log.notes = body.notes
    if body.duration_minutes is not None:
        log.duration_minutes = body.duration_minutes
    if body.next_action is not None:
        log.next_action = body.next_action
    if body.next_action_date is not None:
        log.next_action_date = datetime.fromisoformat(body.next_action_date)

    await db.commit()
    return JSONResponse(content={"ok": True, "message": "Call log updated"})


@router.delete("/calls/{log_id}", dependencies=[Depends(verify_token)])
async def delete_call_log(log_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallLog).filter(CallLog.id == log_id))
    log = result.scalars().first()
    if not log:
        raise HTTPException(404, "Call log not found")
    await db.delete(log)
    await db.commit()
    return JSONResponse(content={"ok": True, "message": "Call log deleted"})
