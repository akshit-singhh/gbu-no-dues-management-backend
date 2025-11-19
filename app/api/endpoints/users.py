# app/api/endpoints/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
from sqlmodel import select

from app.api.deps import get_db_session, require_super_admin
from app.schemas.user import UserRead
from app.schemas.auth import RegisterRequest
from app.services.auth_service import get_user_by_email, create_user
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/users", tags=["Users"])


# -------------------------------------------------------------------
# Create ANY user (Super Admin only)
# -------------------------------------------------------------------
@router.post("/", response_model=UserRead)
async def create_new_user(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin)
):
    # Ensure email is unique
    existing = await get_user_by_email(session, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Validate and enforce allowed roles
    if data.role not in UserRole.__members__.values():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{data.role}'. Allowed roles: {[r.value for r in UserRole]}"
        )

    # Create user
    user = await create_user(
        session,
        data.name,
        data.email,
        data.password,
        role=data.role,  # role now comes from body
    )
    return user


# -------------------------------------------------------------------
# List all users (Super Admin only)
# -------------------------------------------------------------------
@router.get("/", response_model=List[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin)
):
    result = await session.execute(select(User))
    return result.scalars().all()


# -------------------------------------------------------------------
# Delete a user (Super Admin only)
# -------------------------------------------------------------------
@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin)
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await session.delete(user)
    await session.commit()
    return {"detail": "User deleted successfully"}
