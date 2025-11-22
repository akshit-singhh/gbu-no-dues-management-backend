from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db_session
from app.core.rbac import AllowRoles
from app.models.user import User, UserRole
from app.models.application import Application
from app.models.application_stage import ApplicationStage
from app.schemas.approval import StageActionRequest, StageActionResponse
from app.services.approval_service import approve_stage, reject_stage

router = APIRouter(
    prefix="/api/approvals",
    tags=["Approvals"]
)

# -------------------------------------------------------------------
# LIST ALL APPLICATIONS
# -------------------------------------------------------------------
@router.get("/all")
async def list_all_applications(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office, UserRole.CellMember)),
):

    result = await session.execute(select(Application))
    apps = result.scalars().all()

    return apps


# -------------------------------------------------------------------
# GET APPLICATION + STAGES
# -------------------------------------------------------------------
@router.get("/{app_id}")
async def get_application_details(
    app_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office, UserRole.CellMember)),
):
    # Application
    result = await session.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Stages
    stages_result = await session.execute(
        select(ApplicationStage)
        .where(ApplicationStage.application_id == app.id)
        .order_by(ApplicationStage.sequence_order.asc())
    )
    stages = stages_result.scalars().all()

    return {
        "application": app,
        "stages": stages
    }


# -------------------------------------------------------------------
# APPROVE A STAGE
# -------------------------------------------------------------------
@router.post("/{stage_id}/approve", response_model=StageActionResponse)
async def approve_stage_endpoint(
    stage_id: str,
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office, UserRole.CellMember)),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        stage = await approve_stage(session, stage_id, str(current_user.id))
        return StageActionResponse.from_orm(stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------------
# REJECT A STAGE
# -------------------------------------------------------------------
@router.post("/{stage_id}/reject", response_model=StageActionResponse)
async def reject_stage_endpoint(
    stage_id: str,
    data: StageActionRequest,
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office, UserRole.CellMember)),
    session: AsyncSession = Depends(get_db_session),
):
    if not data.remarks:
        raise HTTPException(status_code=400, detail="Remarks required for rejection")

    try:
        stage = await reject_stage(session, stage_id, str(current_user.id), data.remarks)
        return StageActionResponse.from_orm(stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
