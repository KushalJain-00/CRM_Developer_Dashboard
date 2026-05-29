from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone
from db.models import User

async def upsert_user(db: AsyncSession, email: str, name: str = None, provider_uid: str = None) -> User:
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()
    
    if user:
        user.last_login = datetime.utcnow()
        if name:
            user.name = name
        if provider_uid:
            user.provider_uid = provider_uid
    else:
        user = User(email=email, name=name, provider_uid=provider_uid, last_login=datetime.utcnow())
        db.add(user)
        
    await db.commit()
    await db.refresh(user)
    return user
