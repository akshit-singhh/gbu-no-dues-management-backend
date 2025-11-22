# app/services/student_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
import uuid

from app.models.student import Student
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.schemas.student import StudentRegister, StudentUpdate


# ------------------------------------------------------------
# REGISTER STUDENT + LINKED USER ACCOUNT
# ------------------------------------------------------------
async def register_student_and_user(session: AsyncSession, data: StudentRegister) -> Student:
    """
    Registration stores only minimal fields:

        - enrollment_number
        - roll_number
        - full_name
        - mobile_number
        - email
        - password   (User)
    """

    # -----------------------------
    # 1) CREATE STUDENT
    # -----------------------------
    student = Student(
        enrollment_number=data.enrollment_number,
        roll_number=data.roll_number,
        full_name=data.full_name,
        mobile_number=data.mobile_number,
        email=data.email,
    )

    session.add(student)

    try:
        await session.flush()   # generate student.id
    except IntegrityError as e:
        await session.rollback()
        msg = str(e.orig).lower()

        if "enrollment_number" in msg:
            raise ValueError("Enrollment number already exists")
        if "roll_number" in msg:
            raise ValueError("Roll number already exists")
        if "email" in msg:
            raise ValueError("Email already exists")

        raise ValueError("Failed to create student record")

    # -----------------------------
    # 2) CREATE LINKED USER ACCOUNT
    # -----------------------------
    user = User(
        id=uuid.uuid4(),
        name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.Student.value,  # ENUM FIXED
        student_id=student.id,
    )

    session.add(user)

    try:
        await session.commit()
        await session.refresh(student)
        return student

    except IntegrityError as e:
        await session.rollback()
        msg = str(e.orig).lower()

        if "email" in msg:
            raise ValueError("User email already exists")

        raise ValueError("Failed to create user account")


# ------------------------------------------------------------
# UPDATE STUDENT LIMITED FIELDS (USED DURING APPLICATION SUBMISSION)
# ------------------------------------------------------------
async def update_student_for_application(
    session: AsyncSession,
    student_id: uuid.UUID,
    update_data: StudentUpdate
) -> Student:

    result = await session.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    if not student:
        raise ValueError("Student not found")

    # Apply only fields provided (ignore None)
    update_dict = update_data.dict(exclude_unset=True)

    for key, value in update_dict.items():
        setattr(student, key, value)

    try:
        await session.commit()
        await session.refresh(student)
        return student

    except IntegrityError:
        await session.rollback()
        raise ValueError("Failed to update student details")


# ------------------------------------------------------------
# GET STUDENT BY ID
# ------------------------------------------------------------
async def get_student_by_id(session: AsyncSession, student_id: str) -> Student | None:
    result = await session.execute(select(Student).where(Student.id == student_id))
    return result.scalar_one_or_none()


# ------------------------------------------------------------
# LIST ALL STUDENTS
# ------------------------------------------------------------
async def list_students(session: AsyncSession) -> list[Student]:
    result = await session.execute(select(Student))
    return result.scalars().all()
