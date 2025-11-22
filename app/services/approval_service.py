from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models.application_stage import ApplicationStage
from app.models.application import Application

async def approve_stage(session: AsyncSession, stage_id: str, reviewer_id: str):
    # 1. Fetch stage
    result = await session.execute(
        select(ApplicationStage).where(ApplicationStage.id == stage_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise ValueError("Stage not found")

    if stage.status == "Approved":
        raise ValueError("Stage already approved")

    # 2. Approve stage
    stage.status = "Approved"
    stage.reviewer_id = reviewer_id
    stage.reviewed_at = datetime.utcnow()

    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


async def reject_stage(session: AsyncSession, stage_id: str, reviewer_id: str, remarks: str):
    # 1. Fetch stage
    result = await session.execute(
        select(ApplicationStage).where(ApplicationStage.id == stage_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise ValueError("Stage not found")

    # 2. Reject stage
    stage.status = "Rejected"
    stage.remarks = remarks
    stage.reviewer_id = reviewer_id
    stage.reviewed_at = datetime.utcnow()

    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage
