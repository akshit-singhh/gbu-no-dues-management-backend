from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session
from app.core.config import settings
from app.core.rate_limiter import limiter 
from app.core.security import create_access_token
from app.models.student import Student
from app.models.user import User

# Schemas
from app.schemas.auth import (
    StudentLoginRequest, 
    StudentLoginResponse, 
    StudentRegisterRequest
)

# Services
from app.services.auth_service import (
    authenticate_student, 
    get_user_by_email, 
    create_student
)
from app.services.email_service import send_welcome_email
from app.services.turnstile import verify_turnstile
from app.services.audit_service import log_system_event 

router = APIRouter(prefix="/api/students", tags=["Auth (Students)"])

# ----------------------------------------------------------------
# 1. STUDENT REGISTRATION (Public)
# ----------------------------------------------------------------
@router.post("/register", response_model=StudentLoginResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute") 
async def register_student(
    request: Request,
    data: StudentRegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Registers a new student, creates a User account, and auto-logins.
    """
    
    # 1. Turnstile Verification
    client_ip = request.client.host if request.client else None
    
    if not data.turnstile_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security check missing. Please refresh."
        )

    is_human = await verify_turnstile(data.turnstile_token, ip=client_ip)
    if not is_human:
        # Log bot registration attempts
        background_tasks.add_task(
            log_system_event,
            event_type="SECURITY_CHECK_FAILED",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            new_values={"attempted_email": data.email, "reason": "Turnstile validation failed (Student Register)"},
            status="FAILURE"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Security check failed. Please refresh and try again."
        )

    # 2. Perform Registration
    try:
        created_student = await create_student(
            session=session,
            enrollment_number=data.enrollment_number,
            roll_number=data.roll_number,
            full_name=data.full_name,
            email=data.email,
            mobile_number=data.mobile_number,
            password=data.password,
            school_code=data.school_code,
            school_id=data.school_id
        )
        
        # 3. Reload Student
        refresh_query = (
            select(Student)
            .options(selectinload(Student.school))
            .where(Student.id == created_student.id)
        )
        refresh_res = await session.execute(refresh_query)
        student = refresh_res.scalar_one()

        # 4. Fetch User
        user = await get_user_by_email(session, student.email)
        if not user:
            raise HTTPException(500, "Account created but user link failed.")
        # 6. Generate Token
        access_token = create_access_token(
            subject=str(user.id),
            data={
                "role": "student",
                "student_id": str(student.id),
                "school_id": student.school_id
            }
        )

        # 7. Prepare Response
        student_dict = student.model_dump()
        student_dict["school_name"] = student.school.name if student.school else "Unknown School"

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user.id,
            "student_id": student.id,
            "student": student_dict
        }

    # Let HTTPExceptions (like 400 Already Registered) bubble up!
    except HTTPException as http_ex:
        raise http_ex 

    # Catch Service-level ValueErrors and turn them into 400s
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Only catch unexpected errors as 500
    except Exception as e:
        print(f"Registration Unexpected Error: {e}") 
        raise HTTPException(status_code=500, detail="Registration failed due to a server error.")


# ----------------------------------------------------------------
# 2. STUDENT LOGIN
# ----------------------------------------------------------------
@router.post("/login", response_model=StudentLoginResponse)
@limiter.limit("5/minute") 
async def student_login_endpoint(
    request: Request, 
    data: StudentLoginRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session)
):
    # 1. Turnstile Verification
    client_ip = request.client.host if request.client else None
    
    if not data.turnstile_token:
        raise HTTPException(status_code=400, detail="Security check missing.")

    is_human = await verify_turnstile(data.turnstile_token, ip=client_ip)
    if not is_human:
        # Log bot login attempts
        background_tasks.add_task(
            log_system_event,
            event_type="SECURITY_CHECK_FAILED",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            new_values={"attempted_identifier": data.identifier, "reason": "Turnstile validation failed (Student Login)"},
            status="FAILURE"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Security check failed. Please refresh and try again."
        )

    # 2. Auth Logic
    auth = await authenticate_student(session, data.identifier, data.password)

    if not auth:
        # Log failed logins to track password guessing / brute force
        background_tasks.add_task(
            log_system_event,
            event_type="LOGIN_FAILED",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            new_values={"attempted_identifier": data.identifier, "target": "Student Account"},
            status="FAILURE"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid credentials. Please check your Roll No / Enrollment No and password."
        )

    return auth