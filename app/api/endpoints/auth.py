# app/api/endpoints/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
from uuid import UUID
from app.services.auth_service import authenticate_user, create_login_response

from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenWithUser
)
from app.schemas.user import UserRead, UserUpdate
from app.services.auth_service import (
    authenticate_user,
    create_user,
    create_access_token,
    get_user_by_email,
    list_users,
    delete_user_by_id,
    update_user
)
from app.api.deps import get_db_session, get_current_user, require_super_admin
from app.models.user import UserRole, User


router = APIRouter(prefix="/api/auth", tags=["Auth (Super Admin)"])


# ------------------------------------------------------------
# LOGIN  (UPDATED: returns TokenWithUser)
# ------------------------------------------------------------
@router.post("/login", response_model=TokenWithUser)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    user = await authenticate_user(session, payload.email, payload.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return create_login_response(user)


# ------------------------------------------------------------
# REGISTER SUPER ADMIN (Protected)
# ------------------------------------------------------------
@router.post("/register-super-admin", response_model=UserRead)
async def register_super_admin(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    existing = await get_user_by_email(session, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await create_user(
        session=session,
        name=data.name,
        email=data.email,
        password=data.password,
        role=UserRole.super_admin,
    )
    return user


# ------------------------------------------------------------
# REGISTER OTHER USERS (Protected)
# ------------------------------------------------------------
@router.post("/register-user", response_model=UserRead)
async def register_user(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    if data.role == UserRole.super_admin:
        raise HTTPException(
            status_code=400,
            detail="Cannot create super admin via this endpoint"
        )

    existing = await get_user_by_email(session, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await create_user(
        session=session,
        name=data.name,
        email=data.email,
        password=data.password,
        role=data.role,
    )
    return user


# ------------------------------------------------------------
# LIST USERS (Super Admin Only)
# ------------------------------------------------------------
@router.get("/users", response_model=List[UserRead])
async def get_all_users(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    users = await list_users(session)
    return users


# ------------------------------------------------------------
# DELETE USER
# ------------------------------------------------------------
@router.delete("/users/{user_id}", status_code=204)
async def remove_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    try:
        await delete_user_by_id(session, str(user_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return None


# ------------------------------------------------------------
# UPDATE USER
# ------------------------------------------------------------
@router.put("/users/{user_id}", response_model=UserRead)
async def update_user_endpoint(
    user_id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    try:
        user = await update_user(
            session,
            user_id=user_id,
            name=data.name,
            email=data.email,
            role=data.role,
            department_id=data.department_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return user


# ------------------------------------------------------------
# ME
# ------------------------------------------------------------
@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
