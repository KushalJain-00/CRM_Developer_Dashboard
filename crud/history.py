from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from db.models import SessionData, Record, User, Contact, CallLog
from typing import Optional, List


async def list_sessions(db: AsyncSession, email: Optional[str] = None, limit: int = 50):
    q = select(SessionData)
    if email:
        result = await db.execute(select(User).filter(User.email == email))
        u = result.scalars().first()
        if u:
            q = q.filter(or_(SessionData.user_id == u.id, SessionData.user_id.is_(None)))
    q = q.order_by(SessionData.upload_date.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def get_session(db: AsyncSession, session_id: int):
    result = await db.execute(select(SessionData).filter(SessionData.id == session_id))
    return result.scalars().first()


async def get_session_records(db: AsyncSession, session_id: int, page: int = 1, page_size: int = 100):
    count_result = await db.execute(
        select(func.count()).select_from(Record).filter(Record.session_id == session_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Record).filter(Record.session_id == session_id)
        .offset((page - 1) * page_size).limit(page_size)
    )
    records = result.scalars().all()
    return total, records


async def delete_session(db: AsyncSession, session_id: int) -> bool:
    result = await db.execute(select(SessionData).filter(SessionData.id == session_id))
    s = result.scalars().first()
    if not s:
        return False
    await db.delete(s)
    await db.commit()
    return True


async def get_all_session_records(db: AsyncSession, session_id: int) -> List[Record]:
    result = await db.execute(
        select(Record).filter(Record.session_id == session_id)
    )
    return result.scalars().all()


async def find_contacts_by_emails(db: AsyncSession, emails: List[str]) -> List[Contact]:
    contacts = []
    for i in range(0, len(emails), 2000):
        chunk = emails[i:i + 2000]
        result = await db.execute(select(Contact).filter(Contact.email_primary.in_(chunk)))
        contacts.extend(result.scalars().all())
    return contacts


async def find_contacts_by_phones(db: AsyncSession, phones: List[str]) -> List[Contact]:
    contacts = []
    for i in range(0, len(phones), 2000):
        chunk = phones[i:i + 2000]
        result = await db.execute(select(Contact).filter(Contact.phone_primary.in_(chunk)))
        contacts.extend(result.scalars().all())
    return contacts


async def get_call_logs_for_contacts(db: AsyncSession, contact_ids: List[int]) -> dict:
    logs_by_contact = {}
    for i in range(0, len(contact_ids), 2000):
        chunk = contact_ids[i:i + 2000]
        result = await db.execute(
            select(CallLog).filter(CallLog.contact_id.in_(chunk)).order_by(CallLog.call_date.desc())
        )
        for log in result.scalars().all():
            if log.contact_id not in logs_by_contact:
                logs_by_contact[log.contact_id] = []
            logs_by_contact[log.contact_id].append(log)
    return logs_by_contact
