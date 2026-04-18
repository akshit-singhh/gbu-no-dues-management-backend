# app/services/approval_service.py

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from uuid import UUID
from loguru import logger 

from app.models.application import Application, ApplicationStatus
from app.models.application_stage import ApplicationStage
from app.models.user import User, UserRole
from app.models.student import Student

# 1. IMPORT PDF SERVICE
from app.services.pdf_service import generate_certificate_pdf

# ----------------------------------------------------------------
# 1. WATERFALL STATUS UPDATER (Recursive Check + Locking)
# ----------------------------------------------------------------
async def _update_application_status(session: AsyncSession, application_id: UUID, trigger_user_id: UUID = None):
    """
    Checks if the application can move to the next level.
    Uses a WHILE loop to 'waterfall' through multiple completed levels at once.
    """
    # 1. Fetch Application WITH LOCK (Prevents Race Conditions)
    app_res = await session.execute(
        select(Application)
        .where(Application.id == application_id)
        .with_for_update()
    )
    app = app_res.scalar_one()

    # 2. START WATERFALL LOOP
    # Keep checking levels until we hit a "Pending" stage or "Completion"
    while True:
        current_level = app.current_stage_order
        
        # Stop if already completed
        if app.status == ApplicationStatus.COMPLETED.value:
            break

        # A. Fetch Stages for CURRENT Level
        # (This handles both Single Stages like Dean AND Parallel Stages like Administration Depts)
        current_stages_res = await session.execute(
            select(ApplicationStage)
            .where(
                (ApplicationStage.application_id == application_id) &
                (ApplicationStage.sequence_order == current_level)
            )
        )
        current_stages = current_stages_res.scalars().all()

        # B. Check Rejections (Immediate Stop)
        rejected_stages = [s for s in current_stages if s.status == ApplicationStatus.REJECTED.value]
        if rejected_stages:
            app.status = ApplicationStatus.REJECTED.value
            reject_notes = "; ".join([f"{s.verifier_role}: {s.comments or 'No remarks'}" for s in rejected_stages])
            app.remarks = f"Rejected at Level {current_level}: {reject_notes}"
            session.add(app)
            break # Exit loop on rejection

        # C. Check Pending (Immediate Stop)
        # If ANY stage in the current level is still pending, we wait.
        if any(s.status == ApplicationStatus.PENDING.value for s in current_stages):
            # Ensure status is synced to IN_PROGRESS if we are waiting
            if app.status != ApplicationStatus.IN_PROGRESS.value:
                app.status = ApplicationStatus.IN_PROGRESS.value
                session.add(app)
            break # Exit loop, we are stuck here waiting for user action

        # D. All Approved? -> PREPARE TO MOVE UP
        # Find next level strictly greater than current
        next_stage_res = await session.execute(
            select(ApplicationStage)
            .where(
                (ApplicationStage.application_id == application_id) &
                (ApplicationStage.sequence_order > current_level)
            )
            .order_by(ApplicationStage.sequence_order.asc())
        )
        next_stage = next_stage_res.scalars().first()

        if next_stage:
            # MOVE UP and CONTINUE LOOP
            # This unlocks the next level. The loop will run again to check if *that* level is auto-completable.
            logger.info(f"🚀 App {app.display_id}: Level {current_level} Complete. Moving to Level {next_stage.sequence_order}")
            app.current_stage_order = next_stage.sequence_order
            app.status = ApplicationStatus.IN_PROGRESS.value
            session.add(app)
        else:
            # NO NEXT STAGE -> FINISH
            logger.success(f"✅ App {app.display_id} is FULLY APPROVED. Certificate Issued.")
            app.status = ApplicationStatus.COMPLETED.value
            app.is_completed = True
            app.current_stage_order = 999 # Marker for completion
            app.remarks = "All stages cleared. Certificate Issued."
            
            session.add(app)
            await session.flush() 

            # Trigger Certificate Generation
            try:
                await generate_certificate_pdf(session, app.id, trigger_user_id)
            except Exception as e:
                logger.error(f"⚠️ Certificate Generation Failed: {e}")
            
            break # Exit loop

    app.updated_at = datetime.utcnow()
    session.add(app)


# ----------------------------------------------------------------
# HELPER: FETCH REVIEWER
# ----------------------------------------------------------------
async def _fetch_user(session: AsyncSession, reviewer_id):
    if not isinstance(reviewer_id, UUID):
        reviewer_id = UUID(str(reviewer_id))
    result = await session.execute(select(User).where(User.id == reviewer_id))
    return result.scalar_one_or_none()


# ----------------------------------------------------------------
# ACTION: APPROVE STAGE
# ----------------------------------------------------------------
async def approve_stage(session: AsyncSession, stage_id: str, reviewer_id):
    stage_uuid = UUID(stage_id) if isinstance(stage_id, str) else stage_id

    # 1. Fetch Stage + App + Student
    query = (
        select(ApplicationStage, Application, Student)
        .join(Application, ApplicationStage.application_id == Application.id)
        .join(Student, Application.student_id == Student.id)
        .where(ApplicationStage.id == stage_uuid)
    )
    result = await session.execute(query)
    row = result.first()

    if not row:
        raise ValueError("Stage not found")

    stage, application, student = row

    if stage.status == ApplicationStatus.APPROVED.value: 
        raise ValueError("Already approved.")

    # CRITICAL CHECK: Ensure application is actually AT this level
    # This prevents HOD (Seq 2) from approving before Office (Seq 1) is done.
    if stage.sequence_order != application.current_stage_order:
         raise ValueError(f"Cannot approve: Application is at Level {application.current_stage_order}, but this stage is Level {stage.sequence_order}.")

    reviewer = await _fetch_user(session, reviewer_id)
    if not reviewer: 
        raise ValueError("Reviewer user not found")

    # ---------------------------------------------------------
    # PERMISSION CHECKS (Updated for Flow B)
    # ---------------------------------------------------------
    
    # 1. ADMIN (God Mode - Can override anything)
    if reviewer.role == UserRole.Admin:
        pass 

    # 2. DEAN (Matches Student's School)
    elif reviewer.role == UserRole.Dean:
        if not getattr(reviewer, 'school_id', None):
             raise ValueError("Your Dean account has no School assigned.")
        
        # Verify Dean belongs to the same school as the student
        if reviewer.school_id != student.school_id:
             raise ValueError("You are not the Dean of this student's school.")

    # 3. HOD (Matches Stage's Academic Department)
    elif reviewer.role == UserRole.HOD:
        if not getattr(reviewer, 'department_id', None):
             raise ValueError("Your HOD account has no Department assigned.")
        
        # Verify HOD matches the stage's department
        if reviewer.department_id != stage.department_id:
             raise ValueError("You are not the HOD of this department.")

    # 4. STAFF (Handles both School Office & Admin Depts)
    elif reviewer.role == UserRole.Staff:
        
        # CASE A: SCHOOL OFFICE STAFF (Seq 1)
        # They have a School ID but NO Department ID
        if getattr(reviewer, 'school_id', None) and not getattr(reviewer, 'department_id', None):
            if not stage.school_id:
                 raise ValueError("School Office Staff can only approve School-level stages.")
            if reviewer.school_id != stage.school_id:
                 raise ValueError("You do not belong to the School for this stage.")

        # CASE B: DEPARTMENT STAFF (Library, Sports, Accounts - Seq 4 & 5)
        # They have a Department ID
        elif getattr(reviewer, 'department_id', None):
            if not stage.department_id:
                 raise ValueError("Department Staff cannot approve School-level stages.")
            if reviewer.department_id != stage.department_id:
                 raise ValueError("You do not belong to the department for this stage.")
        
        # CASE C: INVALID STAFF CONFIG
        else:
             raise ValueError("Your Staff account has no valid Department or School assignment.")

    # 5. FALLBACK (Legacy or Role Mismatch)
    else:
        # Generic check if roles match exact strings
        reviewer_role_str = reviewer.role.value if hasattr(reviewer.role, "value") else reviewer.role
        if stage.verifier_role != reviewer_role_str:
            raise ValueError(f"Access Denied: You are {reviewer_role_str}, but this stage requires {stage.verifier_role}.")

    # ---------------------------------------------------------
    # UPDATE STAGE
    # ---------------------------------------------------------
    stage.status = ApplicationStatus.APPROVED.value
    stage.verified_by = reviewer.id
    stage.verified_at = datetime.utcnow()
    stage.comments = "Approved via Portal"
    
    session.add(stage)

    # CRITICAL: Flush stage update so _update_application_status sees the change
    await session.flush()
    
    # Update Global Status (This uses the LOCK to prevent race conditions)
    await _update_application_status(session, stage.application_id, trigger_user_id=reviewer.id)

    # Commit everything
    await session.commit()
    await session.refresh(stage)
    
    return stage


# ----------------------------------------------------------------
# ACTION: REJECT STAGE
# ----------------------------------------------------------------
async def reject_stage(session: AsyncSession, stage_id: str, reviewer_id, remarks: str):
    stage_uuid = UUID(stage_id) if isinstance(stage_id, str) else stage_id

    result = await session.execute(
        select(ApplicationStage, Application)
        .join(Application, ApplicationStage.application_id == Application.id)
        .where(ApplicationStage.id == stage_uuid)
    )
    row = result.first()
    
    if not row: raise ValueError("Stage not found")
    stage, application = row

    if stage.sequence_order != application.current_stage_order:
        raise ValueError("Cannot reject: Application is not currently at this stage level.")

    reviewer = await _fetch_user(session, reviewer_id)
    if not reviewer: raise ValueError("Reviewer user not found")

    # Update Stage
    stage.status = ApplicationStatus.REJECTED.value
    stage.comments = remarks
    stage.verified_by = reviewer.id
    stage.verified_at = datetime.utcnow()
    
    session.add(stage)
    await session.flush()
    
    # Update Global Status (Will mark App as REJECTED)
    await _update_application_status(session, stage.application_id, trigger_user_id=reviewer.id)

    await session.commit()
    await session.refresh(stage)

    return stage