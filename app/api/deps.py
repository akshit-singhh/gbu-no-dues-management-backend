# app/api/deps.py

from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.core.database import get_session
from app.services.auth_service import get_user_by_email, get_user_by_id
from app.models.user import User, UserRole

# -------------------------------
# HTTP Bearer for token auth
# -------------------------------
bearer_scheme = HTTPBearer(auto_error=True)

# -------------------------------
# Database dependency
# -------------------------------
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session

# -------------------------------
# Get current authenticated user
# -------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)

        # NEW: Correct field → user ID is stored in "sub"
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    # Fetch user by ID
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# -------------------------------
# Role-based checks
# -------------------------------
def require_role(required_role: str):
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {required_role} role"
            )
        return current_user
    return role_checker


# Exposed role dependencies
require_super_admin = require_role(UserRole.super_admin.value)
require_hod = require_role(UserRole.hod.value)
require_staff = require_role(UserRole.staff.value)
require_office = require_role(UserRole.office.value)
require_student = require_role(UserRole.student.value)
require_office = require_role(UserRole.office.value)

