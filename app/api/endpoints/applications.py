from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationRead
from app.services.application_service import create_application, get_application_by_id


router = APIRouter(
    prefix="/api/applications",
    tags=["Applications"]
)


# ------------------------------------------------------------
# CREATE APPLICATION
# Allowed roles: student, office, super_admin
# ------------------------------------------------------------
@router.post("/", response_model=ApplicationRead)
async def create_new_application(
    data: ApplicationCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    allowed_roles = ["student", "office", "super_admin"]

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Only Students, Office staff, or Super Admin can create applications"
        )

    app = await create_application(
        session=session,
        student_id=str(data.student_id),
        created_by_role=current_user.role,
        created_by_user_id=str(current_user.id),
        remarks=data.remarks
    )

    return app


# ------------------------------------------------------------
# GET APPLICATION BY ID (all roles allowed if authorized)
# ------------------------------------------------------------
@router.get("/{app_id}", response_model=ApplicationRead)
async def get_application(
    app_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    app = await get_application_by_id(session, str(app_id))

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    return app
