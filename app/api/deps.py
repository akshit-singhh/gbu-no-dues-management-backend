# app/api/deps.py

from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.security import decode_token
from app.services.auth_service import get_user_by_id
from app.models.user import User, UserRole
from app.models.application import Application 

from app.core.database import get_db_session 

# ------------------------------------------------------------
# HTTP Bearer Authentication
# ------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=True)


# ------------------------------------------------------------
# Get current logged-in user from JWT
# ------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:

    token = credentials.credentials

    try:
        # Decode token (Will raise PyJWT errors if invalid/expired)
        payload = decode_token(token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"Auth Error: {str(e)}") # Debug log
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user by ID
    user = await get_user_by_id(session, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ------------------------------------------------------------
# Role-based access control
# ------------------------------------------------------------
def role_required(*allowed_roles: UserRole):
    def normalize_role(role):
        if isinstance(role, UserRole):
            return role.value.strip().lower()
        return str(role).strip().lower()

    normalized_allowed = set(normalize_role(r) for r in allowed_roles)

    async def checker(current_user: User = Depends(get_current_user)):
        user_role_normalized = normalize_role(current_user.role)

        if user_role_normalized not in normalized_allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied for role '{current_user.role.value if isinstance(current_user.role, UserRole) else current_user.role}'"
            )

        return current_user

    return checker


# ------------------------------------------------------------
# Exposed dependencies for routers
# ------------------------------------------------------------

# 1. Primary Admin Dependency
# Use this in all new code
require_admin = role_required(UserRole.Admin)

# 2. Backward Compatibility Alias 
# This prevents "ImportError" in other files that might still call 'require_super_admin'
# It simply redirects them to the new Admin logic.
require_super_admin = require_admin

# 3. Other Roles
require_dean = role_required(UserRole.Dean)
require_staff = role_required(UserRole.Staff)
require_student = role_required(UserRole.Student)


# =================================================================
# SMART APPLICATION RESOLVER
# =================================================================
async def get_application_or_404(
    application_id: str = Path(..., description="UUID or Display ID (e.g., ND235...)"),
    session: AsyncSession = Depends(get_db_session)
) -> Application:
    """
    Dependency that finds an application by EITHER:
    1. UUID (Internal ID)
    2. Display ID (Human Readable ID like ND235ICS066A7)
    
    Raises 404 immediately if not found.
    """
    
    # 1. Check format
    is_uuid = False
    try:
        uuid_obj = UUID(application_id)
        is_uuid = True
    except ValueError:
        is_uuid = False
    
    # 2. Build Query
    if is_uuid:
        # Exact UUID Match (Fastest)
        query = select(Application).where(Application.id == uuid_obj)
    else:
        # Smart Display ID Match (Case Insensitive)
        query = select(Application).where(Application.display_id == application_id.upper())
    
    # 3. Execute
    result = await session.execute(query)
    app = result.scalar_one_or_none()
    
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    return app