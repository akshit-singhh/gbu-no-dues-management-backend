from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_ 
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
import uuid

from app.models.student import Student
from app.models.user import User, UserRole
from app.models.school import School
from app.models.department import Department
from app.core.security import get_password_hash
from app.schemas.student import StudentRegister, StudentUpdate


# ------------------------------------------------------------
# REGISTER STUDENT + LINKED USER ACCOUNT
# ------------------------------------------------------------
async def register_student_and_user(session: AsyncSession, data: StudentRegister) -> Student:
    """
    Registers a student and creates a linked user account.
    Resolves School Code to ID and prevents duplicates.
    """

    # -----------------------------
    # 0) RESOLVE SCHOOL CODE -> ID
    # -----------------------------
    final_school_id = data.school_id
    
    # If frontend sent a code (e.g., "SOICT"), look up the ID
    if data.school_code:
        stmt = select(School).where(School.code == data.school_code.strip().upper())
        school_res = await session.execute(stmt)
        school = school_res.scalar_one_or_none()
        
        if not school:
             raise ValueError(f"Invalid School Code: {data.school_code}")
        final_school_id = school.id

    # Fallback validation
    if not final_school_id:
         raise ValueError("School selection is required (ID or Code).")

    # -----------------------------
    # 1) CHECK USER ACCOUNT (Fail Fast)
    # -----------------------------
    # Check User table first. If this email exists, no point checking Student table.
    user_check = await session.execute(select(User).where(User.email == data.email))
    if user_check.scalar_one_or_none():
        raise ValueError("User account with this email already exists.")

    # -----------------------------
    # 2) DUPLICATE STUDENT CHECK
    # -----------------------------
    query = select(Student).where(
        or_(
            Student.roll_number == data.roll_number,
            Student.enrollment_number == data.enrollment_number,
            Student.email == data.email
        )
    )
    result = await session.execute(query)
    existing = result.scalars().first()

    if existing:
        if existing.roll_number == data.roll_number:
            raise ValueError(f"Roll Number '{data.roll_number}' is already registered.")
        elif existing.enrollment_number == data.enrollment_number:
            raise ValueError(f"Enrollment Number '{data.enrollment_number}' is already registered.")
        elif existing.email == data.email:
            raise ValueError(f"Email '{data.email}' is already registered.")

    # -----------------------------
    # 3) CREATE STUDENT
    # -----------------------------
    student = Student(
        enrollment_number=data.enrollment_number,
        roll_number=data.roll_number,
        full_name=data.full_name,
        mobile_number=data.mobile_number,
        email=data.email,
        school_id=final_school_id, # Using Resolved ID
        
        # Safe Mapping (Defaults to None if field missing in Schema)
        father_name=getattr(data, 'father_name', None),
        mother_name=getattr(data, 'mother_name', None),
        admission_year=getattr(data, 'admission_year', None),
        is_hosteller=getattr(data, 'is_hosteller', False),
        hostel_name=getattr(data, 'hostel_name', None),
        hostel_room=getattr(data, 'hostel_room', None),
        batch=getattr(data, 'batch', None),
        section=getattr(data, 'section', None),
        admission_type=getattr(data, 'admission_type', None)
    )

    session.add(student)

    try:
        await session.flush() # Generates student.id
    except IntegrityError as e:
        await session.rollback()
        # Clean up error message
        msg = str(e.orig).lower() if hasattr(e, 'orig') else str(e)
        if "enrollment_number" in msg: raise ValueError("Enrollment number conflict.")
        if "roll_number" in msg: raise ValueError("Roll number conflict.")
        raise ValueError(f"Database error: {msg}")

    # -----------------------------
    # 4) CREATE LINKED USER
    # -----------------------------
    user = User(
        id=uuid.uuid4(),
        name=data.full_name,
        email=data.email,
        password_hash=get_password_hash(data.password),
        role=UserRole.Student,
        student_id=student.id, # Link to the student we just created
        school_id=final_school_id, 
        is_active=True
    )

    session.add(user)

    try:
        await session.commit()
        await session.refresh(student)
        return student

    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"Failed to create user account: {str(e)}")


# ------------------------------------------------------------
# UPDATE STUDENT PROFILE (Smart Update)
# ------------------------------------------------------------
async def update_student_profile(
    session: AsyncSession, 
    student_id: uuid.UUID, 
    update_data: StudentUpdate
) -> Student:

    result = await session.execute(
        select(Student)
        .where(Student.id == student_id)
        .options(selectinload(Student.school), selectinload(Student.department))
    )
    student = result.scalar_one_or_none()

    if not student:
        raise ValueError("Student not found")

    # Only update provided fields
    update_dict = update_data.model_dump(exclude_unset=True)

    # -----------------------------
    # RESOLVE DEPARTMENT CODE -> ID
    # -----------------------------
    if "department_code" in update_dict:
        dept_code = update_dict.pop("department_code")
        if dept_code:
            dept_res = await session.execute(select(Department).where(Department.code == dept_code))
            dept = dept_res.scalar_one_or_none()
            if dept:
                student.department_id = dept.id
            else:
                raise ValueError(f"Invalid Department Code: {dept_code}")

    # -----------------------------
    # STANDARD FIELDS UPDATE
    # -----------------------------
    for key, value in update_dict.items():
        if hasattr(student, key):
            setattr(student, key, value)

    try:
        await session.commit()
        await session.refresh(student)
        return student

    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"Update failed (Integrity Error): {str(e)}")


# ------------------------------------------------------------
# GET STUDENT BY ID
# ------------------------------------------------------------
async def get_student_by_id(session: AsyncSession, student_id: uuid.UUID) -> Student | None:
    # Eager load school/dept to prevent relationship errors
    result = await session.execute(
        select(Student)
        .where(Student.id == student_id)
        .options(selectinload(Student.school), selectinload(Student.department))
    )
    return result.scalar_one_or_none()


# ------------------------------------------------------------
# LIST ALL STUDENTS
# ------------------------------------------------------------
async def list_students(session: AsyncSession) -> list[Student]:
    result = await session.execute(
        select(Student)
        .options(selectinload(Student.school))
    )
    return result.scalars().all()