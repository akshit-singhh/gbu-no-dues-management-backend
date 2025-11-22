# app/api/endpoints/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
from uuid import UUID

# Schemas
from app.schemas.auth import LoginRequest, RegisterRequest, TokenWithUser
from app.schemas.user import UserRead, UserUpdate
from app.schemas.student import StudentRead

# Models
from app.models.user import UserRole, User

# Services
from app.services.auth_service import (
    authenticate_user,
    create_login_response,
    create_user,
    get_user_by_email,
    list_users,
    delete_user_by_id,
    update_user
)
from app.services.student_service import (
    get_student_by_id,
    list_students
)

# Deps
from app.api.deps import get_db_session, get_current_user, require_super_admin


router = APIRouter(prefix="/api/admin", tags=["Auth (Super Admin)"])


# -------------------------------------------------------------------
# LOGIN (Admin login)
# -------------------------------------------------------------------
@router.post("/login", response_model=TokenWithUser)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session)
):
    user = await authenticate_user(session, payload.email, payload.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return create_login_response(user)


# -------------------------------------------------------------------
# REGISTER SUPER ADMIN  (Only existing Admin can do this)
# -------------------------------------------------------------------
@router.post("/register-super-admin", response_model=UserRead)
async def register_super_admin(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    if data.role != UserRole.Admin:
        raise HTTPException(400, detail="This endpoint can only create Admin accounts.")

    # Check duplicate
    existing = await get_user_by_email(session, data.email)
    if existing:
        raise HTTPException(400, "Email already exists")

    user = await create_user(
        session=session,
        name=data.name,
        email=data.email,
        password=data.password,
        role=UserRole.Admin
    )
    return user


# -------------------------------------------------------------------
# REGISTER ANY USER (Except Admin)
# -------------------------------------------------------------------
@router.post("/register-user", response_model=UserRead)
async def register_user(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    # Admin cannot use this endpoint
    if data.role == UserRole.Admin:
        raise HTTPException(400, detail="Use /register-super-admin to create admin accounts.")

    # Validate existing email
    existing = await get_user_by_email(session, data.email)
    if existing:
        raise HTTPException(400, "Email already exists")

    # Create user
    user = await create_user(
        session=session,
        name=data.name,
        email=data.email,
        password=data.password,
        role=data.role
    )
    return user


# -------------------------------------------------------------------
# LIST ALL USERS (Admin Only)
# -------------------------------------------------------------------
@router.get("/users", response_model=List[UserRead])
async def get_all_users(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    return await list_users(session)


# -------------------------------------------------------------------
# DELETE USER
# -------------------------------------------------------------------
@router.delete("/users/{user_id}", status_code=204)
async def remove_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    try:
        await delete_user_by_id(session, str(user_id))
    except ValueError as e:
        raise HTTPException(404, detail=str(e))

    return None


# -------------------------------------------------------------------
# UPDATE USER
# -------------------------------------------------------------------
@router.put("/users/{user_id}", response_model=UserRead)
async def update_user_endpoint(
    user_id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    try:
        return await update_user(
            session,
            user_id=user_id,
            name=data.name,
            email=data.email,
            role=data.role,
            department_id=data.department_id
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# -------------------------------------------------------------------
# ME (Get current admin)
# -------------------------------------------------------------------
@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# -------------------------------------------------------------------
# GET STUDENT BY ID (Admin Only)
# -------------------------------------------------------------------
@router.get("/students/{student_id}", response_model=StudentRead)
async def admin_get_student_by_id(
    student_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    student = await get_student_by_id(session, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student


# -------------------------------------------------------------------
# LIST ALL STUDENTS (Admin Only)
# -------------------------------------------------------------------
@router.get("/students", response_model=List[StudentRead])
async def admin_list_students(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_super_admin),
):
    return await list_students(session)
