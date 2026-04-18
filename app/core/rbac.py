# app/core/rbac.py

from fastapi import Depends, HTTPException, status
from app.api.deps import get_current_user
from app.models.user import User, UserRole

def AllowRoles(*allowed_roles):
    """
    Flexible RBAC:
    - Accepts UserRole values or raw strings
    - Case-insensitive
    - Admin bypasses everything
    """

    def normalize(role) -> str:
        if isinstance(role, UserRole):
            return role.value.lower().strip()
        return str(role).lower().strip()

    normalized_allowed = {normalize(r) for r in allowed_roles}

    async def role_checker(current_user: User = Depends(get_current_user)):
        if not current_user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthenticated")

        user_role_raw = current_user.role
        user_role = normalize(user_role_raw)

        # Admin bypass
        if user_role == "admin":
            return current_user

        if user_role not in normalized_allowed:
            readable_role = (
                user_role_raw.value if isinstance(user_role_raw, UserRole)
                else str(user_role_raw)
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{readable_role}'"
            )

        return current_user

    return role_checker
