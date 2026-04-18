# app/api/endpoints/students.py
from sqlmodel import select

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session
from app.core.rbac import AllowRoles
from app.models.student import Student
from app.models.user import User, UserRole
from app.schemas.student import StudentRead, StudentUpdate

from app.services.student_service import (
    get_student_by_id,
    update_student_profile
)

router = APIRouter(
    prefix="/api/students",
    tags=["Students (Profile)"]
)

# ------------------------------------------------------------
# GET "MY PROFILE"
# ------------------------------------------------------------
@router.get("/me", response_model=StudentRead)
async def get_my_student_profile(
    current_user: User = Depends(AllowRoles(UserRole.Student, UserRole.Admin)),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Fetch the currently logged-in student's profile details.
    """
    if not current_user.student_id:
        raise HTTPException(status_code=404, detail="Student profile not linked to this account")
    stmt = (
        select(Student)
        .options(
            selectinload(Student.school),
            selectinload(Student.department),
            selectinload(Student.programme),
            selectinload(Student.specialization)
        )
        .where(Student.id == current_user.student_id)
    )
    
    result = await session.execute(stmt)
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student record not found in database")

    # Now Pydantic can read data.programme without triggering a lazy DB call
    return StudentRead.model_validate(student)


# ------------------------------------------------------------
# UPDATE PROFILE (General Update)
# ------------------------------------------------------------
@router.patch("/update", response_model=StudentRead)
async def update_my_profile(
    update_data: StudentUpdate,
    current_user: User = Depends(AllowRoles(UserRole.Student)),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Allows the student to update their profile details (Address, Mobile, etc.)
    independently of the application process.
    """
    if not current_user.student_id:
        raise HTTPException(status_code=404, detail="Student profile not linked")

    try:
        # 1. Update the student (this modifies the DB but might not eager-load relationships)
        await update_student_profile(
            session, 
            current_user.student_id, 
            update_data
        )
        
        stmt = (
            select(Student)
            .options(
                selectinload(Student.school),
                selectinload(Student.department),
                selectinload(Student.programme),
                selectinload(Student.specialization)
            )
            .where(Student.id == current_user.student_id)
        )
        result = await session.execute(stmt)
        full_updated_student = result.scalar_one()

        return StudentRead.model_validate(full_updated_student)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))