# app/api/endpoints/account.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db_session
from app.core.security import verify_password, hash_password
from app.models.user import User

router = APIRouter(prefix="/api/account", tags=["Account"])


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    # Verify old password
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Old password incorrect")

    # Prevent reusing old password
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")

    # Update password
    current_user.password_hash = hash_password(payload.new_password)
    session.add(current_user)
    await session.commit()

    return {"detail": "Password changed successfully"}
