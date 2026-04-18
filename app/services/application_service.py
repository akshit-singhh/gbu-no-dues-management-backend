from sqlmodel import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import uuid
from datetime import datetime
from typing import Optional

from app.models.application import Application, ApplicationStatus
from app.models.application_stage import ApplicationStage
from app.models.student import Student
from app.models.department import Department
from app.models.user import UserRole
from app.schemas.application import ApplicationCreate
from loguru import logger

async def create_application_for_student(
    session: AsyncSession,
    student_id: str,
    payload: ApplicationCreate
) -> Application:

    # 1. Fetch Student & Pre-load School
    stmt = (
        select(Student)
        .where(Student.id == student_id)
        .options(selectinload(Student.school)) 
    )
    student_res = await session.execute(stmt)
    student = student_res.scalar_one_or_none()
    
    if not student:
        raise ValueError("Student not found")

    # 2. Resolve Academic Department
    if payload.department_code:
        dept_res = await session.execute(
            select(Department).where(Department.code == payload.department_code.upper().strip())
        )
        academic_dept = dept_res.scalar_one_or_none()
        
        if not academic_dept:
            raise HTTPException(status_code=400, detail=f"Invalid Department Code")
        
        student.department_id = academic_dept.id
    else:
        if not student.department_id:
             raise HTTPException(status_code=400, detail="Academic Department is required.")

    # 3. Validate Prerequisites
    if not student.school_id:
        raise ValueError("Student has no School assigned.")
    if not student.department_id:
        raise ValueError("Student has no Academic Department assigned.")

    # 4. Check Existing Application
    existing_app_q = await session.execute(
        select(Application)
        .where(Application.student_id == student.id)
        .order_by(Application.created_at.desc())
    )
    existing_app = existing_app_q.scalars().first()

    if existing_app:
        current_status = str(existing_app.status).lower()
        if current_status in [ApplicationStatus.PENDING.value, ApplicationStatus.IN_PROGRESS.value]:
            raise ValueError("You already have an active application.")
        if current_status == ApplicationStatus.COMPLETED.value:
            raise ValueError("You have already received your No Dues certificate.")

    # 5. Update Student Profile
    student.father_name = payload.father_name
    student.mother_name = payload.mother_name
    student.gender = payload.gender
    student.category = payload.category
    student.dob = payload.dob
    student.permanent_address = payload.permanent_address
    student.domicile = payload.domicile
    student.section = payload.section
    student.admission_year = payload.admission_year
    student.admission_type = payload.admission_type
    
    student.is_hosteller = payload.is_hosteller
    if payload.is_hosteller:
        student.hostel_name = payload.hostel_name
        student.hostel_room = payload.hostel_room
    else:
        student.hostel_name = None
        student.hostel_room = None

    session.add(student)

    # 6. Create Application
    app = Application(
        id=uuid.uuid4(),
        student_id=student.id,
        status=ApplicationStatus.PENDING.value,
        current_stage_order=1, 
        remarks=payload.remarks, 
        student_remarks=payload.student_remarks,
        proof_document_url=payload.proof_document_url,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(app)
    await session.flush() 

    # 7. GENERATE STAGES
    dept_res = await session.execute(select(Department))
    all_depts = dept_res.scalars().all()
    dept_map = {d.code: d for d in all_depts}
    
    stages_to_create = []

    # --- NODE 1: SCHOOL OFFICE ---
    stages_to_create.append(ApplicationStage(
        id=uuid.uuid4(), application_id=app.id, school_id=student.school_id,    
        verifier_role=UserRole.Staff, sequence_order=1, status=ApplicationStatus.PENDING.value,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow()
    ))

    # --- NODE 2: HOD ---
    stages_to_create.append(ApplicationStage(
        id=uuid.uuid4(), application_id=app.id, department_id=student.department_id,
        verifier_role=UserRole.HOD, sequence_order=2, status=ApplicationStatus.PENDING.value,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow()
    ))

    # --- NODE 3: SCHOOL DEAN ---
    stages_to_create.append(ApplicationStage(
        id=uuid.uuid4(), application_id=app.id, school_id=student.school_id,   
        verifier_role=UserRole.Dean, sequence_order=3, status=ApplicationStatus.PENDING.value,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow()
    ))

    # --- NODE 4: ADMINISTRATIVE DEPTS ---
    # Phase 2 departments (Library, Labs, Sports, Hostel)
    admin_depts = [d for d in all_depts if d.phase_number == 2]
    
    for dept in admin_depts:
        # A. LAB EXEMPTION (Still Dynamic based on School)
        if dept.code == "LAB":
            if student.school and not student.school.requires_lab_clearance:
                logger.info(f"Skipping LAB stage for student from {student.school.code}")
                continue
            
        # B. HOSTEL EXEMPTION (Based on Student Input)
        if dept.code == "HST" and not payload.is_hosteller:
            continue

        # Note: 'LIB' (Library) is no longer checked. Everyone gets it.

        stages_to_create.append(ApplicationStage(
            id=uuid.uuid4(),
            application_id=app.id,
            department_id=dept.id,      
            verifier_role=UserRole.Staff, 
            sequence_order=4,
            status=ApplicationStatus.PENDING.value,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ))

    # --- NODE 5: ACCOUNTS ---
    if "ACC" in dept_map:
        accounts_dept = dept_map["ACC"]
        stages_to_create.append(ApplicationStage(
            id=uuid.uuid4(), application_id=app.id, department_id=accounts_dept.id,
            verifier_role=UserRole.Staff, sequence_order=5, status=ApplicationStatus.PENDING.value,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow()
        ))
    else:
        logger.error("🚨 CRITICAL: 'ACC' (Accounts) Department missing in Database!")

    session.add_all(stages_to_create)

    # 8. Commit
    try:
        await session.commit()
        await session.refresh(app)
        return app

    except IntegrityError as e:
        await session.rollback()
        logger.error(f"Database Integrity Error: {e}") 
        raise ValueError("Failed to create application due to data conflict.")
    except Exception as e:
        await session.rollback()
        logger.error(f"Unexpected Error: {e}")
        raise e

async def get_application_by_student(session: AsyncSession, student_id: uuid.UUID) -> Optional[Application]:
    query = select(Application).where(Application.student_id == student_id).order_by(Application.created_at.desc())
    result = await session.execute(query)
    return result.scalars().first()