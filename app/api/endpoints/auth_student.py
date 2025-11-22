# app/api/endpoints/auth_student.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.schemas.auth_student import StudentLoginRequest, StudentLoginResponse
from app.services.auth_service import authenticate_student

router = APIRouter(prefix="/api/students", tags=["Students"])

@router.post("/login", response_model=StudentLoginResponse)
async def student_login_endpoint(
    data: StudentLoginRequest,
    session: AsyncSession = Depends(get_db_session)
):
    auth = await authenticate_student(
        session,
        data.identifier,
        data.password
    )

    if not auth:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return auth




