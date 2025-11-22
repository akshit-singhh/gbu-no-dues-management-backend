# app/services/department_service.py

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.models.application_stage import ApplicationStage

async def list_pending_for_department(session: AsyncSession, dept_id: int):
    result = await session.execute(
        select(ApplicationStage).where(
            (ApplicationStage.department_id == dept_id) &
            (ApplicationStage.status == "Pending")
        ).order_by(ApplicationStage.sequence_order.asc())
    )
    return result.scalars().all()


async def get_stage(session: AsyncSession, stage_id: str):
    result = await session.execute(
        select(ApplicationStage).where(ApplicationStage.id == stage_id)
    )
    return result.scalar_one_or_none()


async def approve_stage(session: AsyncSession, stage: ApplicationStage, reviewer_id: str, remarks: str | None):
    stage.status = "Approved"
    stage.reviewer_id = reviewer_id
    stage.remarks = remarks
    stage.reviewed_at = datetime.utcnow()

    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


async def reject_stage(session: AsyncSession, stage: ApplicationStage, reviewer_id: str, remarks: str | None):
    stage.status = "Rejected"
    stage.reviewer_id = reviewer_id
    stage.remarks = remarks
    stage.reviewed_at = datetime.utcnow()

    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage
