# app/services/department_service.py

from sqlmodel import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.models.application_stage import ApplicationStage
from app.models.application import Application, ApplicationStatus
from app.models.user import User, UserRole

async def list_pending_stages(
    session: AsyncSession, 
    user: User
) -> List[ApplicationStage]:
    """
    Fetch pending stages relevant to the logged-in user's Role & Dept/School.
    """
    stmt = (
        select(ApplicationStage)
        .where(ApplicationStage.status == ApplicationStatus.PENDING.value)
        .options(
            selectinload(ApplicationStage.application).selectinload(Application.student),
            selectinload(ApplicationStage.application).selectinload(Application.stages)
        )
    )

    # --------------------------------------------------------
    # FILTER BY ROLE
    # --------------------------------------------------------
    
    if user.role == UserRole.Dean:
        # Dean sees stages for their SCHOOL with role 'dean'
        stmt = stmt.where(
            ApplicationStage.verifier_role == UserRole.Dean,
            ApplicationStage.school_id == user.school_id
        )

    elif user.role == UserRole.HOD:
        # HOD sees stages for their ACADEMIC DEPT with role 'hod'
        stmt = stmt.where(
            ApplicationStage.verifier_role == UserRole.HOD,
            ApplicationStage.department_id == user.department_id
        )

    elif user.role == UserRole.Staff:
        # Staff can be in School Office OR Admin Depts (Library, etc.)
        # We rely on the user's department_id or school_id link
        
        conditions = []
        
        # 1. School Office Staff
        if user.school_id:
            conditions.append(
                (ApplicationStage.school_id == user.school_id) & 
                (ApplicationStage.verifier_role == UserRole.Staff)
            )
            
        # 2. Department Staff (Library, Sports, Accounts, etc.)
        if user.department_id:
            conditions.append(
                (ApplicationStage.department_id == user.department_id) & 
                (ApplicationStage.verifier_role == UserRole.Staff)
            )
            
        if not conditions:
            return [] # Staff with no assignment sees nothing
            
        # Combine conditions with OR (in case a user has both?)
        from sqlalchemy import or_
        stmt = stmt.where(or_(*conditions))

    else:
        # Admin sees all? Or nothing?
        # Usually Admins use a different endpoint. Return empty for safety.
        return []

    # Execute
    result = await session.execute(stmt)
    stages = result.scalars().all()
    
    # --------------------------------------------------------
    # POST-FILTER: ENFORCE SEQUENCE
    # --------------------------------------------------------
    # We only show stages where the *previous* stages are completed.
    # (Flow: Dean(1) -> HOD(2) -> Office(3) -> Lib/Sports(4) -> Accounts(5))
    
    actionable_stages = []
    
    for stage in stages:
        app = stage.application
        if not app or not app.stages:
            continue
            
        # Check if all lower sequence stages are 'approved'
        # e.g. If I am Sequence 3, Sequence 1 and 2 must be approved.
        current_seq = stage.sequence_order
        can_act = True
        
        for s in app.stages:
            if s.sequence_order < current_seq and s.status != "approved":
                can_act = False
                break
        
        if can_act:
            actionable_stages.append(stage)

    return actionable_stages

async def verify_stage(
    session: AsyncSession,
    stage_id: UUID,
    verifier_id: UUID,
    action: str, # "approve" or "reject"
    comments: Optional[str] = None
) -> ApplicationStage:
    
    # 1. Fetch Stage
    result = await session.execute(
        select(ApplicationStage)
        .where(ApplicationStage.id == stage_id)
        .options(selectinload(ApplicationStage.application))
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise ValueError("Stage not found")

    if stage.status != ApplicationStatus.PENDING.value:
        raise ValueError("Stage is already processed")

    # 2. Update Stage
    if action == "approve":
        stage.status = "approved"  # Lowercase to match DB convention
    elif action == "reject":
        stage.status = "rejected"
        # Also reject the main application immediately
        stage.application.status = ApplicationStatus.REJECTED.value
        stage.application.remarks = f"Rejected at {stage.verifier_role} stage: {comments}"
        session.add(stage.application)
    else:
        raise ValueError("Invalid action")

    stage.verified_by = verifier_id
    stage.verified_at = datetime.utcnow()
    stage.comments = comments
    
    session.add(stage)
    
    # 3. Check for Application Completion (If Approved)
    if action == "approve":
        # Check if this was the last stage (Accounts - Seq 5)
        # Or check if any pending stages remain
        app = stage.application
        # We need to re-fetch siblings to be sure, but for now logic is:
        # If this is Sequence 5 (Accounts), finish app.
        if stage.sequence_order == 5:
             app.status = ApplicationStatus.COMPLETED.value
             session.add(app)

    await session.commit()
    await session.refresh(stage)
    return stage