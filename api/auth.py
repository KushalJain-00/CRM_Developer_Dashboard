from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from core.auth import verify_token
from db.database import get_db
from db.models import User

router = APIRouter()

class UserUpsertRequest(BaseModel):
    email: str
    name: Optional[str] = None
    provider_uid: Optional[str] = None

@router.post("/auth/upsert", dependencies=[Depends(verify_token)])
async def upsert_user(body: UserUpsertRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.email == body.email))
    user = result.scalars().first()

    if user:
        user.last_login = datetime.utcnow()
        if body.name:
            user.name = body.name
        if body.provider_uid:
            user.provider_uid = body.provider_uid
    else:
        user = User(email=body.email, name=body.name, provider_uid=body.provider_uid, last_login=datetime.utcnow())
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return JSONResponse({"ok": True, "user_id": user.id, "email": user.email})
