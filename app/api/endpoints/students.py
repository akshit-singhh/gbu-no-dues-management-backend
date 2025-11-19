from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.student import StudentCreate, StudentRead
from app.services.student_service import create_student, get_student_by_id, list_students


router = APIRouter(
    prefix="/api/students",
    tags=["Students"]
)


# ------------------------------------------------------------
# CREATE STUDENT (Allowed: student, super_admin)
# ------------------------------------------------------------
@router.post("/", response_model=StudentRead)
async def create_student_endpoint(
    data: StudentCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in ["student", "super_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only Students or Super Admin can create student records"
        )

    student = await create_student(session, data)
    return student


# ------------------------------------------------------------
# GET STUDENT BY ID
# ------------------------------------------------------------
@router.get("/{student_id}", response_model=StudentRead)
async def get_student(
    student_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    student = await get_student_by_id(session, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student


# ------------------------------------------------------------
# LIST ALL STUDENTS (Super Admin only)
# ------------------------------------------------------------
@router.get("/", response_model=list[StudentRead])
async def list_all_students(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "super_admin":
        raise HTTPException(403, "Only Super Admin can list all students")

    return await list_students(session)
