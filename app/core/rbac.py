# app/core/rbac.py

from fastapi import Depends, HTTPException, status
from app.api.deps import get_current_user
from app.models.user import User, UserRole


def AllowRoles(*allowed_roles):
    """
    Role-based access control.

    - Accepts UserRole enums AND raw strings.
    - Case-insensitive.
    - Admin always has full access.
    """

    # Normalize allowed roles (enum or string) to lowercase strings
    normalized_allowed = set(
        (role.value if isinstance(role, UserRole) else str(role)).strip().lower()
        for role in allowed_roles
    )

    async def role_checker(current_user: User = Depends(get_current_user)):

        # Normalize user's role from DB
        user_role = str(current_user.role).strip().lower()

        # ADMIN BYPASS
        if user_role == "admin":
            return current_user

        # Check allowed
        if user_role not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{current_user.role}'"
            )

        return current_user

    return role_checker
