# app/api/endpoints/approvals.py

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import or_, and_, cast, String
from uuid import UUID
from typing import Optional, Any
from datetime import datetime

from app.api.deps import get_db_session, get_application_or_404, get_current_user
from app.core.rbac import AllowRoles
from app.models.user import User, UserRole
from app.models.application import Application, ApplicationStatus
from app.models.application_stage import ApplicationStage
from app.models.student import Student
from app.models.school import School
from app.models.department import Department
from app.models.audit import AuditLog 
from app.schemas.approval import StageActionRequest, StageActionResponse, AdminOverrideRequest
from app.services.audit_service import log_activity, log_system_event
from fastapi import Request # Ensure Request is imported for IP logging
from app.core.storage import download_from_ftp
# Services
from app.services.approval_service import approve_stage, reject_stage, _update_application_status
from app.services.email_service import send_application_rejected_email, send_application_approved_email
from app.services.pdf_service import generate_certificate_pdf
from app.services.audit_service import log_activity

from app.core.storage import get_signed_url

router = APIRouter(
    prefix="/api/approvals",
    tags=["Approvals"]
)

# Roles permitted to access approval endpoints
VERIFIER_ROLES = [
    UserRole.Dean, UserRole.HOD, UserRole.Staff, 
    UserRole.Library, UserRole.Hostel, UserRole.Sports, UserRole.Lab, 
    UserRole.CRC, UserRole.Account
]

# ===================================================================
#  HELPER: Fetch Email Data
# ===================================================================
async def get_email_context(session: AsyncSession, application_id: str, stage: ApplicationStage):
    query = (
        select(Student)
        .join(Application, Application.student_id == Student.id)
        .where(Application.id == UUID(str(application_id)))
    )
    res = await session.execute(query)
    student = res.scalar_one_or_none()

    entity_name = "Authority"
    if stage.department_id:
        d_res = await session.execute(select(Department.name).where(Department.id == stage.department_id))
        entity_name = d_res.scalar_one_or_none() or "Department"
    elif stage.verifier_role:
        entity_name = stage.verifier_role.capitalize()

    return student, entity_name


# ===================================================================
# LIST ALL APPLICATIONS
# ===================================================================
@router.get("/all")
async def list_all_applications(
    status: Optional[str] = Query(None, description="Filter by status (e.g., 'pending', 'approved')"), 
    search: Optional[str] = Query(None, description="Search by Name, Roll No, or Application ID"), 
    current_user: User = Depends(
        AllowRoles(UserRole.Admin, UserRole.Student, *VERIFIER_ROLES)
    ),
    session: AsyncSession = Depends(get_db_session),
):
    # 1. Base Query
    query = (
        select(Application, Student)
        .join(Student, Application.student_id == Student.id)
        .order_by(Application.updated_at.desc()) 
    )

    # -------------------------------------------------------
    # SMART SEARCH LOGIC
    # -------------------------------------------------------
    if search:
        clean_search = search.strip().upper().replace(" ", "").replace("-", "")
        clean_uuid_search = search.strip().lower().replace("-", "")
        query = query.where(
            or_(
                Student.full_name.ilike(f"%{search}%"),
                Student.roll_number.ilike(f"%{search}%"),
                Student.enrollment_number.ilike(f"%{search}%"),
                Application.display_id.ilike(f"%{clean_search}%"),
                cast(Application.id, String).ilike(f"%{clean_uuid_search}%")
            )
        )

    # -------------------------------------------------------
    # LOGIC FOR DEPARTMENTS / VERIFIERS (Strict Filtering)
    # -------------------------------------------------------
    if current_user.role not in [UserRole.Admin, UserRole.Student]:
        query = query.join(ApplicationStage, ApplicationStage.application_id == Application.id)

        # A. DEAN (Only Dean Stages for their School)
        if current_user.role == UserRole.Dean:
            dean_school_id = getattr(current_user, 'school_id', None)
            if not dean_school_id:
                return JSONResponse(status_code=200, content={"message": "Dean has no school assigned.", "data": []})
            
            query = query.where(
                ApplicationStage.school_id == dean_school_id,
                ApplicationStage.verifier_role == "dean" 
            )

        # B. HOD (Only HOD Stages for their Dept)
        elif current_user.role == UserRole.HOD:
            hod_dept_id = getattr(current_user, 'department_id', None)
            if not hod_dept_id:
                return JSONResponse(status_code=200, content={"message": "HOD has no department assigned.", "data": []})
            
            query = query.where(
                ApplicationStage.department_id == hod_dept_id,
                ApplicationStage.verifier_role == "hod"
            )

        # C. STAFF (Distinguish School Office vs Dept Staff)
        elif current_user.role == UserRole.Staff:
            staff_school_id = getattr(current_user, 'school_id', None)
            staff_dept_id = getattr(current_user, 'department_id', None)

            # 1. SCHOOL OFFICE STAFF
            if staff_school_id:
                query = query.where(
                    ApplicationStage.school_id == staff_school_id,
                    ApplicationStage.verifier_role == "staff" 
                )
            
            # 2. DEPARTMENT STAFF (e.g. Library)
            elif staff_dept_id:
                query = query.where(ApplicationStage.department_id == staff_dept_id)
            
            else:
                return JSONResponse(status_code=200, content={"message": "Staff has no department or school assigned.", "data": []})

        # D. OTHER SPECIFIC ROLES (Legacy support)
        else:
            role_name = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
            query = query.where(ApplicationStage.verifier_role == role_name)

        # Status Filter (Applied to the *User's specific stage*)
        if status:
            query = query.where(ApplicationStage.status == status)
        
        # Only show if the workflow has reached this stage (Forward visibility constraint)
        query = query.where(Application.current_stage_order >= ApplicationStage.sequence_order)
        query = query.distinct()

    # -------------------------------------------------------
    # ADMIN & STUDENT
    # -------------------------------------------------------
    elif current_user.role == UserRole.Admin:
        if status:
            query = query.where(Application.status == status)

    elif current_user.role == UserRole.Student:
        query = query.where(Application.student_id == current_user.student_id)
        if status:
            query = query.where(Application.status == status)

    # --- EXECUTE ---
    result = await session.execute(query)
    rows = result.all() 

    if not rows:
        return JSONResponse(status_code=200, content={"message": "No applications found.", "data": []})

    final_list = []
    now = datetime.utcnow()

    for app, student in rows:
        # Location Logic (Summary String)
        current_location_str = "Processing..."
        if app.status == "completed":
            current_location_str = "Completed (Certificate Issued)"
        else:
            active_stages_res = await session.execute(
                select(ApplicationStage, Department.name)
                .outerjoin(Department, ApplicationStage.department_id == Department.id)
                .where(
                    (ApplicationStage.application_id == app.id) &
                    (ApplicationStage.sequence_order == app.current_stage_order)
                )
            )
            active_stages = active_stages_res.all()
            pending_names = []
            approved_names = []
            rejected_names = []

            for stage_obj, dept_name in active_stages:
                name = dept_name if dept_name else stage_obj.verifier_role.replace("_", " ").title()
                if stage_obj.verifier_role == "dean": name = "School Dean"
                
                if stage_obj.status == "approved": approved_names.append(name)
                elif stage_obj.status == "rejected": rejected_names.append(name)
                else: pending_names.append(name)
            
            parts = []
            if rejected_names: parts.append(f"Rejected by: {', '.join(rejected_names)}")
            if pending_names: parts.append(f"Pending at: {', '.join(pending_names)}")
            if approved_names and app.status != "rejected": parts.append(f"Approved by: {', '.join(approved_names)}")
            current_location_str = " | ".join(parts) if parts else "Awaiting Initiation"

        # ---------------------------------------------------------------------
        # ACTIVE STAGE LOGIC
        # ---------------------------------------------------------------------
        stage_query = select(ApplicationStage, User.name).outerjoin(User, ApplicationStage.verified_by == User.id).where(ApplicationStage.application_id == app.id)
        
        # Role Filters... (Same logic as above)
        if current_user.role == UserRole.Admin:
            if app.status not in [ApplicationStatus.COMPLETED, ApplicationStatus.REJECTED]:
                stage_query = stage_query.where(ApplicationStage.sequence_order == app.current_stage_order)
            else:
                stage_query = stage_query.order_by(ApplicationStage.sequence_order.desc())
        elif current_user.role == UserRole.Staff:
            if current_user.school_id:
                 stage_query = stage_query.where(
                     ApplicationStage.school_id == current_user.school_id,
                     ApplicationStage.verifier_role == "staff" 
                 )
            elif current_user.department_id:
                stage_query = stage_query.where(ApplicationStage.department_id == current_user.department_id)
        elif current_user.role == UserRole.Dean:
             stage_query = stage_query.where(ApplicationStage.verifier_role == "dean")
        elif current_user.role == UserRole.HOD:
             if current_user.department_id:
                stage_query = stage_query.where(
                    ApplicationStage.verifier_role == "hod",
                    ApplicationStage.department_id == current_user.department_id
                )
        elif current_user.role != UserRole.Student:
             role_name = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
             stage_query = stage_query.where(ApplicationStage.verifier_role == role_name)
        else:
             stage_query = stage_query.where(ApplicationStage.sequence_order == app.current_stage_order)

        if current_user.role != UserRole.Admin:
            stage_query = stage_query.order_by(ApplicationStage.sequence_order.asc())
            
        stage_res = await session.execute(stage_query)
        row = stage_res.first() 

        active_stage_data = None
        days_pending = 0
        is_overdue = False

        if row:
            stage_obj, verifier_name = row
            
            if stage_obj.status == "pending":
                delta = now - stage_obj.created_at
                days_pending = delta.days
                if days_pending >= 7:
                    is_overdue = True

            active_stage_data = {
                "stage_id": stage_obj.id,
                "status": stage_obj.status,
                "remarks": stage_obj.comments, 
                "verified_by": stage_obj.verified_by,
                "verifier_name": verifier_name,
                "verified_at": stage_obj.verified_at,
                "sequence_order": stage_obj.sequence_order
            }

        final_list.append({
            "application_id": app.id,
            "display_id": app.display_id,
            "student_id": app.student_id,
            "student_name": student.full_name,
            "roll_number": student.roll_number,
            "enrollment_number": student.enrollment_number,
            "student_email": student.email,
            "student_mobile": student.mobile_number,
            "status": app.status, 
            "current_stage": app.current_stage_order, 
            "remarks": app.remarks,
            "current_location": current_location_str,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "active_stage": active_stage_data,
            "days_pending": days_pending,
            "is_overdue": is_overdue
        })

    return final_list


# ===================================================================
# GET ALL STAGES DETAILED
# ===================================================================
@router.get("/{application_id}/stages")
async def get_application_stages_detailed(
    app: Application = Depends(get_application_or_404),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.Student, *VERIFIER_ROLES)),
):
    if current_user.role == UserRole.Student and app.student_id != current_user.student_id:
        raise HTTPException(status_code=403, detail="Access denied")

    query = (
        select(
            ApplicationStage, 
            Department.name.label("dept_name"),
            User.name.label("verifier_name")
        )
        .outerjoin(Department, ApplicationStage.department_id == Department.id)
        .outerjoin(User, ApplicationStage.verified_by == User.id)
        .where(ApplicationStage.application_id == app.id)
        .order_by(ApplicationStage.sequence_order.asc(), ApplicationStage.id.asc())
    )

    result = await session.execute(query)
    rows = result.all()

    stages_data = []
    
    for stage, dept_name, verifier_name in rows:
        display_name = dept_name if dept_name else stage.verifier_role.replace("_", " ").title()
        if stage.verifier_role == "dean": display_name = "School Dean"
        
        stages_data.append({
            "stage_id": stage.id,
            "sequence": stage.sequence_order,
            "role": stage.verifier_role,
            "department_name": display_name,
            "status": stage.status,
            "remarks": stage.comments,
            "verified_by": verifier_name,
            "verified_at": stage.verified_at,
            "is_current": stage.sequence_order == app.current_stage_order,
            "is_pending": stage.status == "pending"
        })

    return {
        "application_id": app.id,
        "display_id": app.display_id, 
        "status": app.status,
        "stages": stages_data
    }


# ===================================================================
# GET PENDING ONLY
# ===================================================================
@router.get("/pending")
async def list_pending_applications(
    current_user: User = Depends(
        AllowRoles(UserRole.Admin, UserRole.Student, *VERIFIER_ROLES)
    ),
    session: AsyncSession = Depends(get_db_session),
):
    return await list_all_applications(
        status="pending", 
        search=None,
        current_user=current_user, 
        session=session
    )

# ===================================================================
# HISTORY (FIXED: Filter by Role to prevent seeing other stages)
# ===================================================================
@router.get("/history")
async def get_my_approval_history(
    current_user: User = Depends(AllowRoles(UserRole.Admin, UserRole.Student, *VERIFIER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(50, le=100)
):
    # Base Query
    query = (
        select(
            AuditLog.action,
            AuditLog.remarks,
            AuditLog.timestamp,
            AuditLog.actor_name,
            AuditLog.actor_role,
            
            Student.full_name,
            Student.roll_number,
            Student.enrollment_number,
            
            Application.id.label("application_id"),
            Application.display_id
        )
        .join(Application, AuditLog.application_id == Application.id)
        .join(Student, Application.student_id == Student.id)
        .where(AuditLog.action.in_([
            "STAGE_APPROVED", "STAGE_REJECTED", "ADMIN_OVERRIDE_APPROVE", "ADMIN_OVERRIDE_REJECT"
        ]))
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )

    # ---------------------------------------------------------
    # SMART FILTERING: Match Role AND Jurisdiction
    # ---------------------------------------------------------
    
    # 1. ADMIN: Sees Everything
    if current_user.role == UserRole.Admin:
        pass 

    # 2. DEAN: Sees actions by DEANS for their School
    elif current_user.role == UserRole.Dean:
        if current_user.school_id:
            query = query.where(
                or_(
                    AuditLog.actor_id == current_user.id,  # My personal actions
                    and_(
                        Student.school_id == current_user.school_id,
                        AuditLog.actor_role == "dean"
                    )
                )
            )
        else:
            query = query.where(AuditLog.actor_id == current_user.id)

    # 3. HOD: Sees actions by HODS for their Dept
    elif current_user.role == UserRole.HOD:
        if current_user.department_id:
            query = query.where(
                or_(
                    AuditLog.actor_id == current_user.id,
                    and_(
                        Student.department_id == current_user.department_id,
                        AuditLog.actor_role == "hod"
                    )
                )
            )
        else:
            query = query.where(AuditLog.actor_id == current_user.id)

    # 4. STAFF (School Office): Sees actions by STAFF for their School
    elif current_user.role == UserRole.Staff and current_user.school_id:
        query = query.where(
            or_(
                AuditLog.actor_id == current_user.id,
                and_(
                    Student.school_id == current_user.school_id,
                    AuditLog.actor_role == "staff"
                )
            )
        )

    # 5. STAFF (Admin Dept) / STUDENT: Strict ID check
    else:
        query = query.where(AuditLog.actor_id == current_user.id)

    # --- EXECUTE ---
    result = await session.execute(query)
    rows = result.all()

    history_data = []
    for row in rows:
        display_action = "Approved"
        if "REJECT" in row.action:
            display_action = "Rejected"
            
        history_data.append({
            "application_id": row.application_id,
            "display_id": row.display_id,
            "student_name": row.full_name,
            "roll_number": row.roll_number,
            "enrollment_number": row.enrollment_number,
            "actor_name": row.actor_name or "Unknown User", 
            "actor_role": row.actor_role or "Staff",
            "action": display_action,
            "original_action_code": row.action,
            "remarks": row.remarks,
            "timestamp": row.timestamp
        })

    return history_data

# ===================================================================
# ENRICHED DETAILS
# ===================================================================
@router.get("/enriched/{application_id}")
async def get_enriched_application_details(
    application_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Any:
    app = await session.get(Application, application_id)
    if not app:
        raise HTTPException(404, "Application not found")

    details_row = (
        await session.execute(
            select(Application, Student, School.name, Department.name, Department.code)
            .join(Student, Student.id == Application.student_id)
            .outerjoin(School, School.id == Student.school_id)
            .outerjoin(Department, Department.id == Student.department_id)
            .where(Application.id == app.id)
        )
    ).first()

    if not details_row:
        raise HTTPException(404, "Application not found")

    app_obj, student, school_name, department_name, department_code = details_row

    role_name = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    has_access = False

    if current_user.role == UserRole.Admin:
        has_access = True
    elif current_user.role == UserRole.Student:
        has_access = app_obj.student_id == current_user.student_id
    elif current_user.role == UserRole.Dean:
        if not current_user.school_id:
            raise HTTPException(403, "Dean has no school assigned.")
        has_access = student.school_id == current_user.school_id
    elif current_user.role == UserRole.HOD:
        if not current_user.department_id:
            raise HTTPException(403, "HOD has no department assigned.")
        has_access = student.department_id == current_user.department_id
    elif current_user.role == UserRole.Staff:
        if current_user.school_id:
            staff_stage = (
                await session.execute(
                    select(ApplicationStage.id)
                    .where(
                        ApplicationStage.application_id == app_obj.id,
                        ApplicationStage.verifier_role == "staff",
                        ApplicationStage.school_id == current_user.school_id,
                        ApplicationStage.sequence_order <= app_obj.current_stage_order,
                    )
                    .limit(1)
                )
            ).first()
            has_access = staff_stage is not None
        elif current_user.department_id:
            staff_stage = (
                await session.execute(
                    select(ApplicationStage.id)
                    .where(
                        ApplicationStage.application_id == app_obj.id,
                        ApplicationStage.department_id == current_user.department_id,
                        ApplicationStage.sequence_order <= app_obj.current_stage_order,
                    )
                    .limit(1)
                )
            ).first()
            has_access = staff_stage is not None
    else:
        role_stage = (
            await session.execute(
                select(ApplicationStage.id)
                .where(
                    ApplicationStage.application_id == app_obj.id,
                    ApplicationStage.verifier_role == role_name,
                    ApplicationStage.sequence_order <= app_obj.current_stage_order,
                )
                .limit(1)
            )
        ).first()
        has_access = role_stage is not None

    if not has_access:
        raise HTTPException(404, "Application not found or access denied")

    response_dict = {
        "application_id": app_obj.id,
        "display_id": app_obj.display_id,
        "application_status": app_obj.status,
        "current_stage_order": app_obj.current_stage_order,
        "created_at": app_obj.created_at,
        "updated_at": app_obj.updated_at,
        "application_remarks": app_obj.remarks,
        "student_remarks": app_obj.student_remarks,
        "proof_document_url": app_obj.proof_document_url,
        "student_name": student.full_name,
        "roll_number": student.roll_number,
        "enrollment_number": student.enrollment_number,
        "student_mobile": student.mobile_number,
        "student_email": student.email,
        "father_name": student.father_name,
        "mother_name": student.mother_name,
        "gender": student.gender,
        "category": student.category,
        "dob": student.dob,
        "permanent_address": student.permanent_address,
        "domicile": student.domicile,
        "is_hosteller": student.is_hosteller,
        "hostel_name": student.hostel_name,
        "hostel_room": student.hostel_room,
        "section": student.section,
        "admission_year": student.admission_year,
        "admission_type": student.admission_type,
        "school_name": school_name,
        "department_name": department_name,
        "department_code": department_code,
    }

    # 3. Fetch Active Stage
    stage_query = select(ApplicationStage).where(ApplicationStage.application_id == app.id)
    
    if current_user.role == UserRole.Dean:
        stage_query = stage_query.where(ApplicationStage.verifier_role == "dean")
    elif current_user.role == UserRole.HOD:
        stage_query = stage_query.where(
            ApplicationStage.verifier_role == "hod",
            ApplicationStage.department_id == current_user.department_id
        )
    elif current_user.role == UserRole.Staff:
        if current_user.school_id:
            stage_query = stage_query.where(
                ApplicationStage.school_id == current_user.school_id,
                ApplicationStage.verifier_role == "staff" 
            )
        elif current_user.department_id:
            stage_query = stage_query.where(
                ApplicationStage.department_id == current_user.department_id
            )
    
    stage_res = await session.execute(stage_query)
    my_stage = stage_res.scalars().first()

    if my_stage:
        response_dict["active_stage"] = {
            "stage_id": my_stage.id,
            "id": my_stage.id,
            "status": my_stage.status,
            "sequence_order": my_stage.sequence_order,
            "remarks": my_stage.comments, 
            "comments": my_stage.comments 
        }
    else:
        response_dict["active_stage"] = None

    if response_dict.get("proof_document_url"):
        raw_url = response_dict["proof_document_url"]
        
        # We assume you imported `get_signed_url` from app.core.storage
        signed_url = get_signed_url(raw_url)
        
        # If the URL is NOT an HTTP link, it's an FTP path.
        # We replace it with a direct call to our new backend download route!
        if signed_url and not signed_url.startswith("http"):
            # Change this line back to "applications"
            response_dict["proof_document_url"] = f"/api/applications/{application_id}/proof-document"
        else:
            response_dict["proof_document_url"] = signed_url

    return response_dict

# ===================================================================
# APPROVE STAGE
# ===================================================================
@router.post("/{stage_id}/approve", response_model=StageActionResponse)
async def approve_stage_endpoint(
    stage_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(AllowRoles(UserRole.Admin, *VERIFIER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        try:
            stage_uuid = UUID(stage_id)
        except ValueError:
            raise HTTPException(400, "Invalid stage ID format (must be UUID)")

        stage = await session.get(ApplicationStage, stage_uuid)
        if not stage:
            raise HTTPException(404, "Stage not found")

        is_admin = (current_user.role == UserRole.Admin)

        if is_admin:
            if stage.status != "pending":
                raise HTTPException(400, "Stage is not pending")

            stage.status = "approved"
            stage.verified_by = current_user.id
            stage.verified_at = datetime.utcnow()
            stage.comments = "Approved by Admin"
            session.add(stage)
            await session.flush()
            
            await _update_application_status(session, stage.application_id)
        else:
            stage = await approve_stage(session, str(stage_uuid), current_user.id)

        await session.commit()
        await session.refresh(stage)

        stmt = (
            select(Student, Application)
            .join(Application, Application.student_id == Student.id)
            .where(Application.id == stage.application_id)
        )
        res = await session.execute(stmt)
        row = res.first()
        if not row: raise ValueError("Linked Data not found")
        student, application = row

        background_tasks.add_task(
            log_activity,
            action="STAGE_APPROVED" if not is_admin else "ADMIN_OVERRIDE_APPROVE",
            actor_id=current_user.id,
            actor_role=current_user.role.value if hasattr(current_user.role, "value") else current_user.role,
            actor_name=current_user.name,
            application_id=stage.application_id,
            remarks="Approved via Portal" if not is_admin else "Admin Override Approval",
            details={
                "stage_id": str(stage.id), 
                "student_roll": student.roll_number,
                "display_id": application.display_id
            }
        )

        await session.refresh(application) 

        if str(application.status) == ApplicationStatus.COMPLETED.value:
            try:
                await generate_certificate_pdf(session, application.id, current_user.id)
            except Exception as e:
                print(f"⚠️ Certificate generation failed: {e}")

            email_data = {
                "name": student.full_name,
                "email": student.email,
                "roll_number": student.roll_number,
                "enrollment_number": student.enrollment_number,
                "application_id": str(application.id),
                "display_id": application.display_id 
            }
            background_tasks.add_task(send_application_approved_email, email_data)

        return stage

    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ===================================================================
# REJECT STAGE (FIXED LOGGING CRASH)
# ===================================================================
@router.post("/{stage_id}/reject", response_model=StageActionResponse)
async def reject_stage_endpoint(
    stage_id: str,
    data: StageActionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(AllowRoles(UserRole.Admin, *VERIFIER_ROLES)),
    session: AsyncSession = Depends(get_db_session),
):
    if not data.remarks:
        raise HTTPException(400, "Remarks required")

    try:
        # 1. Validate Stage
        try:
            stage_uuid = UUID(stage_id)
        except ValueError:
            raise HTTPException(400, "Invalid stage ID format (must be UUID)")

        stage = await session.get(ApplicationStage, stage_uuid)
        if not stage:
            raise HTTPException(404, "Stage not found")

        # 2. Perform Rejection (DB Update)
        is_admin = (current_user.role == UserRole.Admin)

        if is_admin:
            if stage.status != "pending":
                raise HTTPException(400, "Stage is not pending")

            stage.status = "rejected"
            stage.verified_by = current_user.id
            stage.verified_at = datetime.utcnow()
            stage.comments = f"Admin Rejected: {data.remarks}"
            session.add(stage)
            
            # Cascade reject the application
            app_to_reject = await session.get(Application, stage.application_id)
            app_to_reject.status = ApplicationStatus.REJECTED
            app_to_reject.remarks = f"Rejected by Admin at Stage {stage.sequence_order}: {data.remarks}"
            session.add(app_to_reject)

        else:
            stage = await reject_stage(session, str(stage_uuid), current_user.id, data.remarks)

        await session.commit() # <--- DATA SAVED HERE
        await session.refresh(stage)

        # -----------------------------------------------------------------
        # 3. ROBUST FETCH (Replaces get_email_context to prevent crashes)
        # -----------------------------------------------------------------
        try:
            stmt = (
                select(Student, Application)
                .join(Application, Application.student_id == Student.id)
                .where(Application.id == stage.application_id)
            )
            res = await session.execute(stmt)
            row = res.first()
            
            if row:
                student, application = row
                
                # --- LOGGING ---
                background_tasks.add_task(
                    log_activity,
                    action="STAGE_REJECTED" if not is_admin else "ADMIN_OVERRIDE_REJECT",
                    actor_id=current_user.id,
                    actor_role=current_user.role.value if hasattr(current_user.role, "value") else current_user.role,
                    actor_name=current_user.name,
                    application_id=stage.application_id,
                    remarks=data.remarks,
                    details={
                        "stage_id": str(stage.id), 
                        "student_roll": student.roll_number,
                        "display_id": application.display_id
                    }
                )

                # --- EMAIL ---
                # Determine sender name safely
                sender_name = "Department"
                if stage.department_id:
                    # Try to fetch department name, fallback gracefully if missing
                    dept_res = await session.execute(select(Department.name).where(Department.id == stage.department_id))
                    sender_name = dept_res.scalar_one_or_none() or "Department"
                elif stage.verifier_role:
                    sender_name = stage.verifier_role.capitalize()

                email_payload = {
                    "name": student.full_name,
                    "email": student.email,
                    "department_name": sender_name,
                    "remarks": data.remarks
                }
                background_tasks.add_task(send_application_rejected_email, email_payload)
                
        except Exception as e:
            # CRITICAL: Catch errors here so the API response doesn't crash 
            # (since DB is already updated)
            print(f"⚠️ Post-Rejection Error (Logs/Email failed): {str(e)}")

        return stage

    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ===================================================================
# ADMIN OVERRIDE
# ===================================================================
@router.post("/admin/override-stage", response_model=StageActionResponse)
async def admin_override_stage_action(
    payload: AdminOverrideRequest,
    request: Request, # ADDED REQUEST FOR IP LOGGING
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(AllowRoles(UserRole.Admin)), 
):
    stage = await session.get(ApplicationStage, payload.stage_id)
    if not stage:
        raise HTTPException(404, "Stage not found")

    stmt = (
        select(Student, Application, Department.name)
        .join(Application, Application.student_id == Student.id)
        .join(ApplicationStage, ApplicationStage.application_id == Application.id)
        .outerjoin(Department, ApplicationStage.department_id == Department.id)
        .where(ApplicationStage.id == stage.id)
    )
    res = await session.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(404, "Linked Application data not found")
        
    student, application_read_only, dept_name = row
    target_entity = dept_name if dept_name else stage.verifier_role.capitalize()
    app_id = application_read_only.id

    action_type = payload.action.lower() 
    
    if action_type == "approve":
        stage.status = "approved"
        stage.verified_by = current_user.id
        stage.verified_at = datetime.utcnow()
        stage.comments = f"ADMIN OVERRIDE: {current_user.name} Override: {payload.remarks}" if payload.remarks else "Approved via Admin Override"
        
        session.add(stage)
        
        if application_read_only.status == ApplicationStatus.REJECTED:
             app_to_revive = await session.get(Application, app_id)
             app_to_revive.status = ApplicationStatus.PENDING
             app_to_revive.remarks = f"{app_to_revive.remarks} | Revived by Admin Override"
             session.add(app_to_revive)

        await session.flush() 
        await _update_application_status(session, app_id, trigger_user_id=current_user.id)
        await session.commit() 
        
        final_app = await session.get(Application, app_id)
        
        if final_app.status == ApplicationStatus.COMPLETED:
            try:
                email_data = {
                    "name": student.full_name,
                    "email": student.email,
                    "roll_number": student.roll_number,
                    "enrollment_number": student.enrollment_number,
                    "application_id": str(final_app.id),
                    "display_id": final_app.display_id 
                }
                background_tasks.add_task(send_application_approved_email, email_data)
            except Exception as e:
                print(f"Email Error: {e}")

    elif action_type == "reject":
        if not payload.remarks or not payload.remarks.strip() or payload.remarks == "Admin Override":
            raise HTTPException(status_code=400, detail="Remarks are mandatory when rejecting.")

        stage.status = "rejected"
        stage.verified_by = current_user.id
        stage.verified_at = datetime.utcnow()
        stage.comments = f"ADMIN OVERRIDE: {payload.remarks}"
        
        app_to_reject = await session.get(Application, app_id)
        app_to_reject.status = ApplicationStatus.REJECTED
        app_to_reject.remarks = f"Rejected via Admin Override: {payload.remarks}"
        
        session.add(stage)
        session.add(app_to_reject)
        await session.commit()
        
        email_data = {
            "name": student.full_name,
            "email": student.email,
            "department_name": f"{target_entity} (Admin Action)",
            "remarks": payload.remarks
        }
        background_tasks.add_task(send_application_rejected_email, email_data)

    else:
        raise HTTPException(400, "Invalid action.")

    # 1. Existing Business Workflow Log
    background_tasks.add_task(
        log_activity,
        action=f"ADMIN_OVERRIDE_{action_type.upper()}",
        actor_id=current_user.id,
        actor_role="admin",
        actor_name=current_user.name,
        application_id=stage.application_id,
        remarks=f"Overrode {target_entity} stage: {payload.remarks}",
        details={"stage_id": str(stage.id), "student_roll": student.roll_number}
    )

    # 2. NEW: System Security Log
    background_tasks.add_task(
        log_system_event,
        event_type="SYSTEM_OVERRIDE",
        actor_id=current_user.id,
        resource_type="ApplicationStage",
        resource_id=str(stage.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        old_values={},
        new_values={"action": action_type.upper(), "target_stage": target_entity, "remarks": payload.remarks},
        status="SUCCESS"
    )

    return {
        "stage_id": stage.id,
        "status": stage.status,
        "verified_at": stage.verified_at,
        "comments": stage.comments,
        "id": stage.id,
        "application_id": stage.application_id,
        "department_id": stage.department_id,
        "verifier_role": stage.verifier_role,
        "sequence_order": stage.sequence_order,
        "created_at": stage.created_at,
        "updated_at": stage.updated_at
    }