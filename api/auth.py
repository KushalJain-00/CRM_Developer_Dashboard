from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from core.auth import verify_token
from db.database import get_db
from crud.auth import upsert_user as crud_upsert_user

router = APIRouter()

class UserUpsertRequest(BaseModel):
    email: str
    name: Optional[str] = None
    provider_uid: Optional[str] = None

@router.post("/auth/upsert", dependencies=[Depends(verify_token)])
async def upsert_user(body: UserUpsertRequest, db: AsyncSession = Depends(get_db)):
    user = await crud_upsert_user(db, email=body.email, name=body.name, provider_uid=body.provider_uid)
    return JSONResponse({"ok": True, "user_id": user.id, "email": user.email})