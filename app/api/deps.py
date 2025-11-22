# app/api/deps.py

from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.core.database import get_session
from app.services.auth_service import get_user_by_id
from app.models.user import User, UserRole


# ------------------------------------------------------------
# HTTP Bearer Authentication
# ------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=True)


# ------------------------------------------------------------
# DB Session
# ------------------------------------------------------------
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


# ------------------------------------------------------------
# Get current logged-in user from JWT
# ------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:

    token = credentials.credentials

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(401, "Invalid token payload")

    except JWTError:
        raise HTTPException(401, "Could not validate credentials")

    # Fetch user by ID
    user = await get_user_by_id(session, user_id)

    if not user:
        raise HTTPException(401, "User not found")

    return user


# ------------------------------------------------------------
# Role-based access control (CASE-SAFE)
# ------------------------------------------------------------
def role_required(*allowed_roles: UserRole):
    """
    Enforces that the current user has one of the allowed roles.
    Matches using actual DB enum values (Admin, HOD, etc.)
    """

    # convert enum to raw values
    allowed = [r.value if isinstance(r, UserRole) else r for r in allowed_roles]

    async def checker(current_user: User = Depends(get_current_user)):
        user_role = current_user.role  # string stored in DB

        if user_role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied for role '{user_role}'"
            )

        return current_user

    return checker


# ------------------------------------------------------------
# Exposed dependencies for routers
# ------------------------------------------------------------

# Admin is the TRUE super-admin
require_super_admin = role_required(UserRole.Admin)

require_hod = role_required(UserRole.HOD)
require_office = role_required(UserRole.Office)
require_cell_member = role_required(UserRole.CellMember)
require_student = role_required(UserRole.Student)
