from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime
from db.models import Company, Contact, CallLog
from typing import Optional


async def create_call_log(db: AsyncSession, contact_id: int, company_id: int,
                          call_type: str, outcome: str, notes: str,
                          duration_minutes: int = None, next_action: str = None,
                          next_action_date: datetime = None, created_by: str = None) -> CallLog:
    log = CallLog(
        contact_id=contact_id,
        company_id=company_id,
        call_type=call_type,
        outcome=outcome,
        notes=notes,
        duration_minutes=duration_minutes,
        next_action=next_action,
        next_action_date=next_action_date,
        created_by=created_by,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def get_call_logs(db: AsyncSession, contact_id: Optional[int] = None,
                        company_id: Optional[int] = None, skip: int = 0, limit: int = 100):
    q = select(CallLog)
    if contact_id:
        q = q.filter(CallLog.contact_id == contact_id)
    if company_id:
        q = q.filter(CallLog.company_id == company_id)
    q = q.order_by(CallLog.call_date.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def update_call_log(db: AsyncSession, log_id: int, **kwargs) -> Optional[CallLog]:
    result = await db.execute(select(CallLog).filter(CallLog.id == log_id))
    log = result.scalars().first()
    if not log:
        return None
    for key, val in kwargs.items():
        if val is not None and hasattr(log, key):
            setattr(log, key, val)
    await db.commit()
    await db.refresh(log)
    return log


async def delete_call_log(db: AsyncSession, log_id: int) -> bool:
    result = await db.execute(select(CallLog).filter(CallLog.id == log_id))
    log = result.scalars().first()
    if not log:
        return False
    await db.delete(log)
    await db.commit()
    return True
