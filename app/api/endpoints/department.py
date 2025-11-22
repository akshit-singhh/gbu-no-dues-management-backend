# app/api/endpoints/department.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import AllowRoles
from app.models.user import User, UserRole
from app.api.deps import get_db_session
from app.services.department_service import (
    list_pending_for_department,
    get_stage,
    approve_stage,
    reject_stage
)

router = APIRouter(
    prefix="/api/department",
    tags=["Department Processing"]
)

# 1️⃣ List pending applications (Admin can see everything too)
@router.get("/applications/pending")
async def get_pending(
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office)),
    session: AsyncSession = Depends(get_db_session)
):
    dept_id = current_user.department_id
    if not dept_id:
        raise HTTPException(400, "User has no department assigned")

    stages = await list_pending_for_department(session, dept_id)
    return stages


# 2️⃣ Approve stage
@router.post("/applications/{stage_id}/approve")
async def approve_stage_endpoint(
    stage_id: str,
    remarks: str | None = None,
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office)),
    session: AsyncSession = Depends(get_db_session)
):
    stage = await get_stage(session, stage_id)
    if not stage:
        raise HTTPException(404, "Stage not found")

    if stage.department_id != current_user.department_id:
        raise HTTPException(403, "Not authorized for this department")

    return await approve_stage(session, stage, current_user.id, remarks)


# 3️⃣ Reject stage
@router.post("/applications/{stage_id}/reject")
async def reject_stage_endpoint(
    stage_id: str,
    remarks: str | None = None,
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.HOD, UserRole.Office)),
    session: AsyncSession = Depends(get_db_session)
):
    stage = await get_stage(session, stage_id)
    if not stage:
        raise HTTPException(404, "Stage not found")

    if stage.department_id != current_user.department_id:
        raise HTTPException(403, "Not authorized for this department")

    return await reject_stage(session, stage, current_user.id, remarks)
