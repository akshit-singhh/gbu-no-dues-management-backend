import random
import string
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy import or_
from uuid import UUID
from typing import Any, List, Optional
from datetime import datetime

# Deps & Auth
from app.api.deps import get_db_session, get_application_or_404, get_current_user
from app.core.rbac import AllowRoles
from app.models.user import User, UserRole
from app.models.department import Department
from app.models.academic import Programme, Specialization# ✅ NEW IMPORT
from app.core.storage import download_from_ftp
# Models & Schemas
from app.models.student import Student 
from app.models.application import Application, ApplicationStatus
from app.models.application_stage import ApplicationStage 

# Utilities & Services
from app.core.storage import get_signed_url
from app.schemas.application import ApplicationCreate, ApplicationRead, ApplicationResubmit
from app.services.application_service import create_application_for_student
from app.services.email_service import send_application_created_email
from app.services.pdf_service import generate_certificate_pdf
from app.services.department_service import list_pending_stages
from fastapi.responses import Response, RedirectResponse
from sqlmodel import select
from app.models.certificate import Certificate

router = APIRouter(
    prefix="/api/applications",
    tags=["Applications"]
)

# ------------------------------------------------------------
# HELPER: Generate Readable ID
# ------------------------------------------------------------
def generate_display_id(roll_number: str) -> str:
    """
    Generates a clean ID: ND235ICS066A7
    """
    clean_roll = roll_number.strip().upper().replace(" ", "").replace("-", "")
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
    return f"ND{clean_roll}{suffix}"


# ===================================================================
# 1. STAFF/FACULTY ENDPOINTS (Approvals)
# ===================================================================

@router.get("/pending", response_model=List[ApplicationStage])
async def get_my_pending_tasks(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Fetches stages waiting for approval by the current user.
    """
    
    # 1. ADMIN (Debug/View All)
    if current_user.role == UserRole.Admin:
        return [] 

    # 2. DEAN (School Level)
    if current_user.role == UserRole.Dean:
        if not current_user.school_id:
             raise HTTPException(400, "Dean account is missing School ID.")
        
        return await list_pending_stages(
            session, 
            user=current_user 
        )

    # 3. HOD (Department Level)
    elif current_user.role == UserRole.HOD:
        if not current_user.department_id:
             raise HTTPException(400, "HOD account is missing Department ID.")
        
        return await list_pending_stages(
            session, 
            user=current_user
        )

    # 4. STAFF
    elif current_user.role == UserRole.Staff:
        if current_user.school_id or current_user.department_id:
            return await list_pending_stages(
                session, 
                user=current_user
            )
        else:
            raise HTTPException(
                status_code=400, 
                detail="Staff account has no Department or School assigned."
            )

    else:
        return []

# ------------------------------------------------------------
# CREATE APPLICATION
# ------------------------------------------------------------
@router.post("/create", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(AllowRoles(UserRole.Student)),
    session: AsyncSession = Depends(get_db_session),
):
    if not current_user.student_id:
        raise HTTPException(status_code=400, detail="No student profile linked to user")

    student_id = current_user.student_id

    # 1. Update Student Profile
    student_res = await session.execute(select(Student).where(Student.id == student_id))
    student = student_res.scalar_one()

    # --- A. DEPARTMENT LOOKUP ---
    if payload.department_code:
        stmt = select(Department).where(Department.code == payload.department_code.upper().strip())
        dept_result = await session.execute(stmt)
        department = dept_result.scalar_one_or_none()

        if not department:
            raise HTTPException(status_code=400, detail=f"Invalid Department Code: {payload.department_code}")

        student.department_id = department.id 
    else:
        # Fallback if student already has it set, otherwise error
        if not student.department_id:
            raise HTTPException(status_code=400, detail="Department Code is required.")
        # If dept not in payload but on student, we need the Dept Object for validation below
        department = await session.get(Department, student.department_id)

    # --- B. PROGRAMME & SPECIALIZATION LOOKUP (NEW) ---
    
    # 1. Programme
    if payload.programme_code:
        stmt = select(Programme).where(Programme.code == payload.programme_code.upper().strip())
        prog_res = await session.execute(stmt)
        programme = prog_res.scalar_one_or_none()
        
        if not programme:
            raise HTTPException(400, f"Invalid Programme Code: {payload.programme_code}")
        
        # Validation: Programme MUST belong to the selected Department
        if department and programme.department_id != department.id:
             raise HTTPException(400, f"Programme '{programme.name}' does not belong to Department '{department.name}'")
             
        student.programme_id = programme.id

    # 2. Specialization (Optional but linked)
    if payload.specialization_code:
        stmt = select(Specialization).where(Specialization.code == payload.specialization_code.upper().strip())
        spec_res = await session.execute(stmt)
        specialization = spec_res.scalar_one_or_none()
        
        if not specialization:
            raise HTTPException(400, f"Invalid Specialization Code: {payload.specialization_code}")
            
        # Validation: Specialization MUST belong to the selected Programme
        # Note: If programme_code wasn't passed, we check against student.programme_id
        current_prog_id = student.programme_id 
        if current_prog_id and specialization.programme_id != current_prog_id:
             raise HTTPException(400, "Selected Specialization does not belong to the selected Programme")

        student.specialization_id = specialization.id

    # --- C. OTHER PROFILE FIELDS ---
    student.father_name = payload.father_name
    student.mother_name = payload.mother_name
    student.gender = payload.gender
    student.category = payload.category
    student.dob = payload.dob
    student.permanent_address = payload.permanent_address
    student.domicile = payload.domicile
    student.is_hosteller = payload.is_hosteller
    
    # Handle Hostel details (Clear if not hosteller)
    if payload.is_hosteller:
        student.hostel_name = payload.hostel_name
        student.hostel_room = payload.hostel_room
    else:
        student.hostel_name = None
        student.hostel_room = None
        
    student.section = payload.section
    student.admission_year = payload.admission_year
    student.admission_type = payload.admission_type
    
    session.add(student)

    # 2. Generate Unique Display ID
    new_display_id = generate_display_id(student.roll_number)
    while True:
        existing = await session.execute(
            select(Application).where(Application.display_id == new_display_id)
        )
        if not existing.scalar_one_or_none():
            break
        new_display_id = generate_display_id(student.roll_number)

    # 3. Create Application (Service logic handles Stage Generation)
    try:
        new_app = await create_application_for_student(
            session=session,
            student_id=student_id,
            payload=payload 
        )

        # 4. Link Extra Details
        new_app.proof_document_url = payload.proof_document_url
        new_app.display_id = new_display_id 
        
        session.add(new_app)
        await session.commit()
        await session.refresh(new_app)

    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await session.rollback()
        print(f"CRITICAL ERROR creating application: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    # 5. Send Email
    if current_user.email:
        email_data = {
            "name": current_user.name,
            "email": current_user.email,
            "application_id": str(new_app.id),
            "display_id": new_display_id 
        }
        background_tasks.add_task(send_application_created_email, email_data)

    return ApplicationRead.model_validate(new_app)


# ------------------------------------------------------------
# GET MY APPLICATION (Updated for Dropdown Filtering)
# ------------------------------------------------------------
@router.get("/my", status_code=200)
async def get_my_application(
    current_user: User = Depends(AllowRoles(UserRole.Student)),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    
    if not current_user.student_id:
        raise HTTPException(status_code=400, detail="No student linked to account")

    # 1. FETCH STUDENT PROFILE FIRST (Needed even if no application exists)
    stmt_student = (
        select(Student)
        .options(
            selectinload(Student.school), # ✅ Ensure School is loaded
            selectinload(Student.department),
            selectinload(Student.programme),
            selectinload(Student.specialization)
        )
        .where(Student.id == current_user.student_id)
    )
    res_student = await session.execute(stmt_student)
    student = res_student.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Prepare Student Data for UI (Available regardless of app status)
    student_data = {
        "full_name": student.full_name,
        "enrollment_number": student.enrollment_number,
        "roll_number": student.roll_number,
        "email": student.email,
        "mobile_number": student.mobile_number,
        
        # ✅ DATA FOR DROPDOWN FILTERING
        "school_id": student.school_id, 
        "school_name": student.school.name if student.school else "N/A",
        "school_code": student.school.code if student.school else "N/A", # ✅ Ensure this is here
        
        "programme_name": student.programme.name if student.programme else "N/A",
        "specialization_name": student.specialization.name if student.specialization else "N/A",
        
        "father_name": student.father_name,
        "hostel_name": student.hostel_name,
        "is_hosteller": student.is_hosteller,
    }

    # 2. FETCH APPLICATION
    stmt_app = (
        select(Application)
        .where(Application.student_id == current_user.student_id)
        .order_by(Application.created_at.desc())
    )
    res_app = await session.execute(stmt_app)
    app = res_app.scalars().first()

    # --- CASE A: NO APPLICATION SUBMITTED YET ---
    if not app:
        return {
            "application": None,
            "message": "No application found.",
            "student": student_data # ✅ Sent so UI can filter Dept Dropdown
        }

    # --- CASE B: APPLICATION EXISTS ---
    
    # Fetch Stages
    stage_result = await session.execute(
        select(ApplicationStage)
        .where(ApplicationStage.application_id == app.id)
        .order_by(ApplicationStage.sequence_order.asc())
    )
    stages = stage_result.scalars().all()

    # Calculate Progress Percentage
    total_stages = len(stages)
    approved_stages = sum(1 for s in stages if str(s.status) == "approved")
    
    if str(app.status) == "completed":
        progress_percentage = 100
    elif total_stages > 0:
        progress_percentage = int((approved_stages / total_stages) * 100)
    else:
        progress_percentage = 0

    # Calculate Flags
    is_rejected = any(s.status == "rejected" for s in stages)
    rejected_stage = next((s for s in stages if s.status == "rejected"), None)
    is_completed = str(app.status) == "completed"

    signed_proof_link = None
    if app.proof_document_url:
        signed_proof_link = get_signed_url(app.proof_document_url)
    
    return {
        "student": student_data,
        "application": {
            "id": app.id,
            "display_id": app.display_id, 
            "status": app.status,
            "current_stage_order": app.current_stage_order,
            "remarks": app.remarks,
            "student_remarks": app.student_remarks,
            "proof_document_url": signed_proof_link, 
            "proof_path": app.proof_document_url,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "progress_percentage": progress_percentage 
        },
        "stages": [
            {
                "id": s.id,
                "verifier_role": s.verifier_role,
                "status": s.status,
                "sequence_order": s.sequence_order,
                "department_id": s.department_id,
                "comments": s.comments, 
                "verified_by": s.verified_by,
                "verified_at": s.verified_at,
            }
            for s in stages
        ],
        "flags": {
            "is_rejected": is_rejected,
            "is_completed": is_completed,
            "is_in_progress": (str(app.status) == "in_progress"),
        },
        "rejection_details": {
            "role": rejected_stage.verifier_role if rejected_stage else None,
            "remarks": rejected_stage.comments if rejected_stage else None
        } if is_rejected else None
    }

# ------------------------------------------------------------
# GET APPLICATION STATUS (Admin Search Logic)
# ------------------------------------------------------------
@router.get("/status", status_code=200)
async def get_application_status(
    # 1. Allow Admin & Student
    current_user: User = Depends(AllowRoles(UserRole.Student, UserRole.Admin)),
    session: AsyncSession = Depends(get_db_session),
    # 2. Admin Search Param (Optional)
    search_query: Optional[str] = None 
) -> Any:
    
    target_student_id = None

    # --- A. STUDENT LOGIC (Unchanged) ---
    if current_user.role == UserRole.Student:
        if not current_user.student_id:
            raise HTTPException(status_code=400, detail="No student linked to account")
        target_student_id = current_user.student_id
    
    # --- B. ADMIN LOGIC (Search for Student) ---
    elif current_user.role == UserRole.Admin:
        if not search_query:
            raise HTTPException(status_code=400, detail="Admin must provide 'search_query' (Roll No, Enrollment No, or ID)")
        
        # Clean the input
        clean_q = search_query.strip()
        
        # Try finding the student using OR operator
        stmt = select(Student).where(
            or_(
                Student.roll_number.ilike(clean_q),       # Case-Insensitive
                Student.enrollment_number.ilike(clean_q), # Case-Insensitive
                
                # Heuristic to check if it's a valid UUID string before casting
                Student.user_id == (UUID(clean_q) if clean_q.replace("-","").isalnum() and len(clean_q) > 20 else None),
                Student.id == (UUID(clean_q) if clean_q.replace("-","").isalnum() and len(clean_q) > 20 else None)
            )
        )
        res = await session.execute(stmt)
        student = res.scalar_one_or_none()
        
        if not student:
            # Fallback: Try partial name match (Case Insensitive)
            stmt = select(Student).where(Student.full_name.ilike(f"%{clean_q}%"))
            res = await session.execute(stmt)
            student = res.scalars().first()

        if not student:
            raise HTTPException(status_code=404, detail=f"Student not found for query: {clean_q}")
            
        target_student_id = student.id
    
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # --- C. FETCH APPLICATION (Common Logic) ---
    result = await session.execute(
        select(Application)
        .where(Application.student_id == target_student_id)
        .order_by(Application.created_at.desc())
        .options(
            # ✅ Eager Load for Admin View too
            selectinload(Application.student).selectinload(Student.programme),
            selectinload(Application.student).selectinload(Student.specialization)
        )
    )
    app = result.scalars().first()

    if not app:
        return {"application": None, "message": "No application found for this student."}

    # --- D. FETCH STAGES (Existing Logic) ---
    stage_result = await session.execute(
        select(ApplicationStage, Department.name)
        .outerjoin(Department, ApplicationStage.department_id == Department.id)
        .where(ApplicationStage.application_id == app.id)
        .order_by(ApplicationStage.sequence_order.asc())
    )
    results = stage_result.all() 
    
    stages_data = []
    current_order = app.current_stage_order
    
    active_pending_names = []
    active_approved_names = []
    active_rejected_names = []
    rejected_stage = None

    for stage, dept_name in results:
        display_name = dept_name if dept_name else stage.verifier_role.replace("_", " ").title()
        if stage.verifier_role == "dean": display_name = "School Dean"

        stages_data.append({
            "id": stage.id,
            "verifier_role": stage.verifier_role,
            "display_name": display_name,
            "status": stage.status,
            "sequence_order": stage.sequence_order,
            "comments": stage.comments,
        })

        if str(stage.status) == str(ApplicationStatus.REJECTED.value):
            rejected_stage = stage
            active_rejected_names.append(display_name)

        if stage.sequence_order == current_order:
            if str(stage.status) == str(ApplicationStatus.PENDING.value):
                active_pending_names.append(display_name)
            elif str(stage.status) == str(ApplicationStatus.APPROVED.value):
                active_approved_names.append(display_name)

    location_str = "Processing..." 
    if str(app.status) == str(ApplicationStatus.REJECTED.value):
        location_str = f"Rejected at: {', '.join(active_rejected_names)}"
    elif str(app.status) == str(ApplicationStatus.COMPLETED.value):
        location_str = "Certificate Ready for Download"
    else:
        parts = []
        if active_pending_names: parts.append(f"Pending at: {', '.join(active_pending_names)}")
        if active_approved_names: parts.append(f"Approved by: {', '.join(active_approved_names)}")
        if parts: location_str = " | ".join(parts)

    return {
        "student_info": { 
             "name": app.student.full_name if app.student else "Student",
             "roll": app.student.roll_number if app.student else "",
             # ✅ Display Prog/Spec in Admin Status View
             "programme": app.student.programme.name if app.student.programme else "N/A",
             "specialization": app.student.specialization.name if app.student.specialization else "N/A",
        },
        "application": {
            "id": app.id,
            "display_id": app.display_id, 
            "status": app.status,
            "current_stage_order": app.current_stage_order,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "current_location": location_str,
            "remarks": app.remarks,
            "student_remarks": app.student_remarks, 
        },
        "stages": stages_data,
        "flags": {
            "is_rejected": (str(app.status) == str(ApplicationStatus.REJECTED.value)),
            "is_completed": (str(app.status) == str(ApplicationStatus.COMPLETED.value)),
            "is_in_progress": (str(app.status) == str(ApplicationStatus.IN_PROGRESS.value)),
        },
        "rejection_details": {
            "role": rejected_stage.verifier_role if rejected_stage else None,
            "remarks": rejected_stage.comments if rejected_stage else None
        } if rejected_stage else None
    }

# ------------------------------------------------------------
# DOWNLOAD CERTIFICATE
# ------------------------------------------------------------
@router.get("/{application_id}/certificate")
async def download_certificate(
    application_id: uuid.UUID,
    app: Application = Depends(get_application_or_404),
    current_user: User = Depends(AllowRoles(UserRole.Student, UserRole.Admin)),
    session: AsyncSession = Depends(get_db_session),
):
    if current_user.role == UserRole.Student:
        if not current_user.student_id:
             raise HTTPException(status_code=403, detail="Student profile missing")
        if str(app.student_id) != str(current_user.student_id):
            raise HTTPException(status_code=403, detail="Not authorized")

    try:
        # 1. Check if the certificate already exists in the database
        stmt = select(Certificate).where(Certificate.application_id == application_id)
        existing_cert = (await session.execute(stmt)).scalar_one_or_none()

        if existing_cert and existing_cert.pdf_url:
            
            # IF CLOUD URL (Supabase/S3): Safe to redirect browser
            if existing_cert.pdf_url.startswith("http"):
                return RedirectResponse(url=existing_cert.pdf_url)
            
            # IF FTP PATH: Fetch bytes from FTP server and stream to browser
            else:
                file_bytes = download_from_ftp(existing_cert.pdf_url)
                
                if not file_bytes:
                    raise HTTPException(status_code=404, detail="File not found on FTP server")
                
                return Response(
                    content=file_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=GBU_No_Dues_{app.display_id or app.id}.pdf"}
                )

        # 2. IF NOT GENERATED YET: Generate for the first time
        pdf_bytes = await generate_certificate_pdf(session, app.id, current_user.id)
        filename = f"GBU_No_Dues_{app.display_id or app.id}.pdf"
        
        # 3. Return the newly generated bytes directly as a downloaded file
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        print(f"Certificate Download Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# -------------------------------------------------------------------
# DOWNLOAD PROOF DOCUMENT
# -------------------------------------------------------------------
@router.get("/{application_id}/proof-document")
async def download_proof_document(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session)
):
    app = await session.get(Application, application_id)
    if not app or not app.proof_document_url:
        raise HTTPException(status_code=404, detail="Proof document not found for this application")

    # 1. Fetch the raw path stored in the database
    raw_path = app.proof_document_url

    # 2. Check if it's a Cloud URL (Supabase) -> Redirect
    if raw_path.startswith("http"):
        signed_url = get_signed_url(raw_path)
        return RedirectResponse(url=signed_url)
        
    # 3. Check if it's an FTP local path -> Download via Backend
    else:
        file_bytes = download_from_ftp(raw_path)
        
        if not file_bytes:
            raise HTTPException(status_code=404, detail="File missing on FTP server")
            
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="Proof_{app.display_id or application_id}.pdf"'
            }
        )


# ------------------------------------------------------------
# RESUBMIT APPLICATION (FIXED FOR HOSTEL LOGIC)
# ------------------------------------------------------------
@router.patch("/{application_id}/resubmit", response_model=ApplicationRead)
async def resubmit_application(
    app: Application = Depends(get_application_or_404),
    payload: ApplicationResubmit = None,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(AllowRoles(UserRole.Student)),
):
    if not payload:
        raise HTTPException(400, "Payload required")

    # 1. Authorization
    if app.student_id != current_user.student_id:
        raise HTTPException(403, "Not authorized to resubmit this application")

    # 2. Validation
    is_globally_rejected = str(app.status) == str(ApplicationStatus.REJECTED.value)
    
    stage_query = select(ApplicationStage).where(
        ApplicationStage.application_id == app.id,
        ApplicationStage.sequence_order == app.current_stage_order,
        ApplicationStage.status == "rejected"
    )
    stage_res = await session.execute(stage_query)
    blocked_stage = stage_res.scalar_one_or_none()

    if not is_globally_rejected and not blocked_stage:
        raise HTTPException(400, "No rejection found. Application is processing.")

    # 3. Update Student Profile
    student = await session.get(Student, app.student_id)
    
    # --- A. DEPT UPDATE ---
    if payload.department_code:
        stmt = select(Department).where(Department.code == payload.department_code.upper().strip())
        dept_result = await session.execute(stmt)
        department = dept_result.scalar_one_or_none()
        if department:
            student.department_id = department.id
        else:
             raise HTTPException(400, f"Invalid Department Code: {payload.department_code}")

    # --- B. PROGRAMME UPDATE (NEW) ---
    if payload.programme_code:
        stmt = select(Programme).where(Programme.code == payload.programme_code.upper().strip())
        prog_res = await session.execute(stmt)
        programme = prog_res.scalar_one_or_none()
        
        if not programme:
            raise HTTPException(400, f"Invalid Programme Code: {payload.programme_code}")
        
        # Verify ownership (Student might have changed Dept too, check against current dept)
        current_dept_id = student.department_id 
        if current_dept_id and programme.department_id != current_dept_id:
             # Try fetching dept name for error msg
             dept = await session.get(Department, current_dept_id)
             raise HTTPException(400, f"Programme '{programme.name}' does not belong to Department '{dept.name}'")
             
        student.programme_id = programme.id

    # --- C. SPECIALIZATION UPDATE (NEW) ---
    if payload.specialization_code:
        stmt = select(Specialization).where(Specialization.code == payload.specialization_code.upper().strip())
        spec_res = await session.execute(stmt)
        specialization = spec_res.scalar_one_or_none()
        
        if not specialization:
            raise HTTPException(400, f"Invalid Specialization Code: {payload.specialization_code}")
            
        current_prog_id = student.programme_id 
        if current_prog_id and specialization.programme_id != current_prog_id:
             raise HTTPException(400, "Selected Specialization does not belong to the selected Programme")

        student.specialization_id = specialization.id

    # --- D. OTHER FIELDS ---
    if payload.father_name is not None: student.father_name = payload.father_name
    if payload.mother_name is not None: student.mother_name = payload.mother_name
    if payload.gender is not None: student.gender = payload.gender
    if payload.category is not None: student.category = payload.category
    if payload.dob is not None: student.dob = payload.dob
    if payload.permanent_address is not None: student.permanent_address = payload.permanent_address
    if payload.domicile is not None: student.domicile = payload.domicile
    if payload.is_hosteller is not None: student.is_hosteller = payload.is_hosteller
    if payload.hostel_name is not None: student.hostel_name = payload.hostel_name
    if payload.hostel_room is not None: student.hostel_room = payload.hostel_room
    if payload.section is not None: student.section = payload.section
    if payload.admission_year is not None: student.admission_year = payload.admission_year
    if payload.admission_type is not None: student.admission_type = payload.admission_type
    
    session.add(student)

    # ---------------------------------------------------------
    # BUG FIX: DYNAMIC HOSTEL STAGE INJECTION/REMOVAL
    # ---------------------------------------------------------
    # Fetch existing stages WITH their department relationship loaded
    stmt_stages = (
        select(ApplicationStage)
        .where(ApplicationStage.application_id == app.id)
        .options(selectinload(ApplicationStage.department)) # Load department to check codes
    )
    res_stages = await session.execute(stmt_stages)
    existing_stages = res_stages.scalars().all()

    # Find if "Hostel" stage exists by checking Dept Code 'HST' or Role Logic
    # We look for a stage linked to the Hostel Department
    hostel_stage = next((s for s in existing_stages if s.department and s.department.code == "HST"), None)

    # CASE A: Student IS now a Hosteller, but NO stage exists -> Inject It
    if student.is_hosteller and not hostel_stage:
        # Find the Hostel Department ID
        dept_q = select(Department).where(Department.code == "HST")
        dept_res = await session.execute(dept_q)
        hostel_dept = dept_res.scalar_one_or_none()

        if hostel_dept:
            new_stage = ApplicationStage(
                application_id=app.id,
                department_id=hostel_dept.id,
                verifier_role="staff",
                # REMOVED: display_name="Hostel Administration", (Since attribute doesn't exist)
                sequence_order=4, # Phase 2 (Parallel) for Flow B
                status="pending"
            )
            session.add(new_stage)
            print(f"✅ Injected missing Hostel Stage for App {app.display_id}")
        else:
            print("⚠️ Critical: Hostel Department 'HST' not found in DB. Cannot create stage.")

    # CASE B: Student is NOT a Hosteller, but stage DOES exist -> Remove It
    elif not student.is_hosteller and hostel_stage:
        await session.delete(hostel_stage)
        print(f"✅ Removed Hostel Stage for App {app.display_id}")

    # ---------------------------------------------------------

    # 4. Handle Remarks
    if payload.student_remarks:
        app.student_remarks = payload.student_remarks

    # 5. Reset Rejected Stage
    if blocked_stage:
        blocked_stage.status = "pending"
        blocked_stage.verified_by = None 
        blocked_stage.verified_at = None
        
        user_note = payload.student_remarks or payload.remarks or "Resubmitted with corrections"
        blocked_stage.comments = f"Resubmission: {user_note}"
        
        session.add(blocked_stage)

    # 6. Update Application (Status & Cleanup)
    app.status = ApplicationStatus.IN_PROGRESS
    app.remarks = ""  # Clear the global rejection remark
    app.updated_at = datetime.utcnow()

    if payload.proof_document_url:
        app.proof_document_url = payload.proof_document_url

    session.add(app)
    await session.commit()
    await session.refresh(app)

    return app