from fastapi import Depends, HTTPException, status
from app.services.auth_service import get_current_user
from app.models.user import UserRole


def role_required(*allowed_roles):
    def wrapper(current_user = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{current_user.role}'",
            )
        return current_user
    return wrapper
