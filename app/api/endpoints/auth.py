import uuid
import csv
import io
import time
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import func, text, case
from sqlalchemy.orm import selectinload
from sqlmodel import select, or_
from sqlmodel.ext.asyncio.session import AsyncSession
from uuid import UUID
from loguru import logger

from app.core.config import settings
from app.core.rate_limiter import limiter
from app.core.security import get_password_hash
from app.core.storage import get_signed_url

# Schemas
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenWithUser,
    SchoolCreateRequest,
    DepartmentCreateRequest,
)
from app.schemas.user import UserRead, UserUpdate, UserListResponse
from app.schemas.student import StudentRead
from app.schemas.audit import AuditLogRead, SystemAuditLogRead
from app.schemas.academic import (
    ProgrammeCreate, ProgrammeRead,
    SpecializationCreate, SpecializationRead,
)

# Models
from app.models.user import UserRole, User
from app.models.school import School
from app.models.department import Department
from app.models.system_audit import SystemAuditLog
from app.models.academic import Programme, Specialization
from app.models.audit import AuditLog
from app.models.application import Application
from app.models.application_stage import ApplicationStage
from app.models.student import Student
from app.models.certificate import Certificate

# Services
from app.services.auth_service import (
    authenticate_user,
    create_login_response,
    create_user,
    get_user_by_email,
    list_users,
    delete_user_by_id,
    update_user,
)
from app.services.student_service import list_students
from app.services.turnstile import verify_turnstile
from app.services.audit_service import log_system_event

from app.api.deps import get_db_session, get_current_user, require_admin

router = APIRouter(prefix="/api/admin", tags=["Auth (Admin)"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """
    Returns the real client IP, accounting for reverse proxies (Vercel, nginx).
    X-Forwarded-For may contain a comma-separated chain — the first entry is the
    original client.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _role_value(role) -> str:
    """Safely extract string value from a UserRole enum or raw string."""
    return role.value if hasattr(role, "value") else role


def _dept_display_name(raw_name: Optional[str]) -> str:
    """Normalize internal department labels into UI-friendly names."""
    value = (raw_name or "").strip().lower()
    if value in {"lab", "labs", "laboratories", "laboratory"}:
        return "Laboratories"
    if value in {"account", "accounts"}:
        return "Accounts"
    if value == "crc":
        return "CRC"
    if value == "dean":
        return "School Dean"
    if value == "hod":
        return "Head of Department"
    if not value:
        return "Unknown"
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


async def _resolve_school_code(session: AsyncSession, code: str) -> School:
    """Resolve a school code to a School ORM object. Raises 400 if not found."""
    res = await session.execute(
        select(School).where(School.code == code.strip().upper())
    )
    school = res.scalar_one_or_none()
    if not school:
        raise HTTPException(status_code=400, detail=f"Invalid School Code: {code.strip().upper()}")
    return school


async def _resolve_dept_code(session: AsyncSession, code: str) -> Department:
    """Resolve a department code to a Department ORM object. Raises 400 if not found."""
    res = await session.execute(
        select(Department).where(Department.code == code.strip().upper())
    )
    dept = res.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=400, detail=f"Invalid Department Code: {code.strip().upper()}")
    return dept


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenWithUser)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
):
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")

    if not payload.turnstile_token:
        raise HTTPException(status_code=400, detail="Security check missing.")

    is_human = await verify_turnstile(payload.turnstile_token, ip=ip)
    if not is_human:
        background_tasks.add_task(
            log_system_event,
            event_type="SECURITY_CHECK_FAILED",
            ip_address=ip,
            user_agent=ua,
            new_values={"attempted_email": payload.email, "reason": "Turnstile validation failed"},
            status="FAILURE",
        )
        raise HTTPException(
            status_code=400,
            detail="Security check failed. Please refresh the page and try again.",
        )

    user = await authenticate_user(session, payload.email, payload.password)
    if not user:
        background_tasks.add_task(
            log_system_event,
            event_type="LOGIN_FAILED",
            ip_address=ip,
            user_agent=ua,
            new_values={"attempted_email": payload.email},
            status="FAILURE",
        )
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    background_tasks.add_task(
        log_system_event,
        event_type="USER_LOGIN",
        actor_id=user.id,
        actor_role=_role_value(user.role),
        ip_address=ip,
        user_agent=ua,
        status="SUCCESS",
    )

    return await create_login_response(user, session)


# ---------------------------------------------------------------------------
# REGISTER USER
# ---------------------------------------------------------------------------

@router.post("/register-user", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    data: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_admin),
):
    existing = await get_user_by_email(session, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists.")

    final_school_id = data.school_id
    final_dept_id = data.department_id

    if data.school_code:
        school = await _resolve_school_code(session, data.school_code)
        final_school_id = school.id

    if data.department_code:
        dept = await _resolve_dept_code(session, data.department_code)
        final_dept_id = dept.id

    # Role-level validation
    if data.role == UserRole.Dean:
        if not final_school_id:
            raise HTTPException(status_code=400, detail="Dean requires a valid 'school_code'.")
        final_dept_id = None  # Deans are school-level, not department-level

    elif data.role == UserRole.HOD:
        if not final_dept_id:
            raise HTTPException(status_code=400, detail="HOD requires a valid 'department_code'.")

    elif data.role == UserRole.Staff:
        if not final_school_id and not final_dept_id:
            raise HTTPException(
                status_code=400,
                detail="Staff must have either 'school_code' or 'department_code'.",
            )
        if final_school_id and final_dept_id:
            raise HTTPException(
                status_code=400,
                detail="Staff cannot operate at both School and Department levels simultaneously.",
            )

    new_user = await create_user(
        session=session,
        name=data.name,
        email=data.email,
        password=data.password,
        role=data.role,
        department_id=final_dept_id,
        school_id=final_school_id,
    )

    background_tasks.add_task(
        log_system_event,
        event_type="USER_CREATED",
        actor_id=current_admin.id,
        actor_role=_role_value(current_admin.role),
        resource_type="User",
        resource_id=str(new_user.id),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_values={"email": new_user.email, "role": _role_value(new_user.role)},
        status="SUCCESS",
    )

    return new_user


# ---------------------------------------------------------------------------
# SCHOOL MANAGEMENT
# ---------------------------------------------------------------------------

@router.post("/schools", status_code=status.HTTP_201_CREATED)
async def create_school(
    payload: SchoolCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    res = await session.execute(
        select(School).where(or_(School.name == payload.name, School.code == payload.code))
    )
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="School with this name or code already exists.")

    new_school = School(
        name=payload.name,
        code=payload.code.upper(),
        requires_lab_clearance=payload.requires_lab_clearance,
    )
    session.add(new_school)
    await session.commit()
    await session.refresh(new_school)
    return new_school


@router.get("/schools", response_model=List[School])
async def list_schools(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    result = await session.execute(select(School).order_by(School.name))
    return result.scalars().all()


@router.delete("/schools/{identifier}", status_code=204)
async def delete_school(
    identifier: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    stmt = (
        select(School).where(School.id == int(identifier))
        if identifier.isdigit()
        else select(School).where(School.code == identifier.upper())
    )
    school = (await session.execute(stmt)).scalar_one_or_none()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    # Explicit pre-check: linked departments
    dept_check = (await session.execute(
        select(Department).where(Department.school_id == school.id).limit(1)
    )).scalar()
    if dept_check:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete {school.code}. Reassign or delete its departments first.",
        )

    # Explicit pre-check: linked users
    user_check = (await session.execute(
        select(User).where(User.school_id == school.id).limit(1)
    )).scalar()
    if user_check:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete {school.code}. Reassign or remove linked staff first.",
        )

    try:
        await session.delete(school)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"School deletion failed for id={school.id}: {e}")
        raise HTTPException(status_code=400, detail="Deletion failed due to remaining linked records.")

    return None


# ---------------------------------------------------------------------------
# DEPARTMENT MANAGEMENT
# ---------------------------------------------------------------------------

@router.post("/departments", status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    res = await session.execute(
        select(Department).where(
            or_(Department.name == payload.name, Department.code == payload.code)
        )
    )
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Department with this name or code already exists.")

    final_school_id = None
    if payload.school_code:
        school = await _resolve_school_code(session, payload.school_code)
        final_school_id = school.id

    if payload.phase_number == 1 and not final_school_id:
        raise HTTPException(
            status_code=400,
            detail="Academic Departments (Phase 1) must be linked to a School.",
        )

    new_dept = Department(
        name=payload.name,
        code=payload.code.upper(),
        phase_number=payload.phase_number,
        school_id=final_school_id,
    )
    session.add(new_dept)
    await session.commit()
    await session.refresh(new_dept)
    return new_dept


@router.get("/departments", response_model=List[Department])
async def list_departments(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    result = await session.execute(
        select(Department)
        .options(selectinload(Department.school))
        .order_by(Department.phase_number, Department.name)
    )
    return result.scalars().all()


@router.delete("/departments/{identifier}", status_code=204)
async def delete_department(
    identifier: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    stmt = (
        select(Department).where(Department.id == int(identifier))
        if identifier.isdigit()
        else select(Department).where(Department.code == identifier.upper())
    )
    dept = (await session.execute(stmt)).scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    # Explicit pre-check: linked students
    student_check = (await session.execute(
        select(Student).where(Student.department_id == dept.id).limit(1)
    )).scalar()
    if student_check:
        raise HTTPException(status_code=400, detail="Cannot delete department: students are linked to it.")

    # Explicit pre-check: linked users
    user_check = (await session.execute(
        select(User).where(User.department_id == dept.id).limit(1)
    )).scalar()
    if user_check:
        raise HTTPException(status_code=400, detail="Cannot delete department: staff are linked to it.")

    try:
        await session.delete(dept)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Department deletion failed for id={dept.id}: {e}")
        raise HTTPException(status_code=400, detail="Deletion failed due to remaining linked records.")

    return None


# ---------------------------------------------------------------------------
# PROGRAMME MANAGEMENT
# ---------------------------------------------------------------------------

@router.post("/programmes", response_model=ProgrammeRead, status_code=status.HTTP_201_CREATED)
async def create_programme(
    payload: ProgrammeCreate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    dept = await _resolve_dept_code(session, payload.department_code)

    existing = (await session.execute(
        select(Programme).where(Programme.code == payload.code.upper().strip())
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Programme Code '{payload.code}' already exists.")

    prog = Programme(
        name=payload.name,
        code=payload.code.upper().strip(),
        department_id=dept.id,
    )
    session.add(prog)
    await session.commit()
    await session.refresh(prog)
    return prog


@router.get("/programmes", response_model=List[ProgrammeRead])
async def list_programmes(
    department_code: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),  # admin-only: under /api/admin
):
    query = (
        select(Programme)
        .options(selectinload(Programme.department))
        .order_by(Programme.name)
    )
    if department_code:
        query = query.join(Department).where(
            Department.code == department_code.upper().strip()
        )

    items = (await session.execute(query)).scalars().all()

    results = []
    for item in items:
        data = item.model_dump()
        data["department_name"] = item.department.name if item.department else "N/A"
        data["department_code"] = item.department.code if item.department else "N/A"
        results.append(data)

    return results


@router.delete("/programmes/{identifier}", status_code=204)
async def delete_programme(
    identifier: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    stmt = (
        select(Programme).where(Programme.id == int(identifier))
        if identifier.isdigit()
        else select(Programme).where(Programme.code == identifier.upper().strip())
    )
    prog = (await session.execute(stmt)).scalar_one_or_none()
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found.")

    student_check = (await session.execute(
        select(Student).where(Student.programme_id == prog.id).limit(1)
    )).scalar()
    if student_check:
        raise HTTPException(status_code=400, detail="Cannot delete Programme: students are enrolled in it.")

    spec_check = (await session.execute(
        select(Specialization).where(Specialization.programme_id == prog.id).limit(1)
    )).scalar()
    if spec_check:
        raise HTTPException(status_code=400, detail="Cannot delete Programme: specializations are linked to it.")

    try:
        await session.delete(prog)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Programme deletion failed for id={prog.id}: {e}")
        raise HTTPException(status_code=500, detail="Internal error during deletion.")

    return None


# ---------------------------------------------------------------------------
# SPECIALIZATION MANAGEMENT
# ---------------------------------------------------------------------------

@router.post("/specializations", response_model=SpecializationRead, status_code=status.HTTP_201_CREATED)
async def create_specialization(
    payload: SpecializationCreate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    prog = (await session.execute(
        select(Programme).where(Programme.code == payload.programme_code.upper().strip())
    )).scalar_one_or_none()
    if not prog:
        raise HTTPException(status_code=400, detail=f"Invalid Programme Code: {payload.programme_code}")

    existing = (await session.execute(
        select(Specialization).where(Specialization.code == payload.code.upper().strip())
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Specialization Code '{payload.code}' already exists.")

    spec = Specialization(
        name=payload.name,
        code=payload.code.upper().strip(),
        programme_id=prog.id,
    )
    session.add(spec)
    await session.commit()
    await session.refresh(spec)
    return spec


@router.get("/specializations", response_model=List[SpecializationRead])
async def list_specializations(
    programme_code: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),  # admin-only: under /api/admin
):
    stmt = (
        select(Specialization)
        .options(selectinload(Specialization.programme))
        .order_by(Specialization.name)
    )
    if programme_code:
        stmt = stmt.join(Programme).where(
            Programme.code == programme_code.upper().strip()
        )

    items = (await session.execute(stmt)).scalars().all()

    results = []
    for item in items:
        data = item.model_dump()
        data["programme_name"] = item.programme.name if item.programme else "N/A"
        data["programme_code"] = item.programme.code if item.programme else "N/A"
        results.append(data)

    return results


@router.delete("/specializations/{identifier}", status_code=204)
async def delete_specialization(
    identifier: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    stmt = (
        select(Specialization).where(Specialization.id == int(identifier))
        if identifier.isdigit()
        else select(Specialization).where(Specialization.code == identifier.upper().strip())
    )
    spec = (await session.execute(stmt)).scalar_one_or_none()
    if not spec:
        raise HTTPException(status_code=404, detail="Specialization not found.")

    student_check = (await session.execute(
        select(Student).where(Student.specialization_id == spec.id).limit(1)
    )).scalar()
    if student_check:
        raise HTTPException(status_code=400, detail="Cannot delete Specialization: students are enrolled in it.")

    try:
        await session.delete(spec)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Specialization deletion failed for id={spec.id}: {e}")
        raise HTTPException(status_code=500, detail="Internal error during deletion.")

    return None


# ---------------------------------------------------------------------------
# USER MANAGEMENT
# ---------------------------------------------------------------------------

@router.get("/users", response_model=UserListResponse)
async def get_all_users(
    role: Optional[UserRole] = Query(None),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    base_query = (
        select(User)
        .options(
            selectinload(User.department),
            selectinload(User.school),
            selectinload(User.student).selectinload(Student.school),
        )
        .order_by(User.created_at.desc())
    )
    if role:
        base_query = base_query.where(User.role == role)

    # Count total without loading all rows
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await session.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    paginated = base_query.limit(page_size).offset(offset)
    users = (await session.execute(paginated)).scalars().all()

    dept_ids = {u.department_id for u in users if u.department_id is not None}
    school_ids = {u.school_id for u in users if u.school_id is not None}
    school_ids.update(
        u.student.school_id
        for u in users
        if u.student is not None and u.student.school_id is not None
    )

    dept_map = {}
    if dept_ids:
        dept_rows = await session.execute(
            select(Department.id, Department.name, Department.code).where(Department.id.in_(dept_ids))
        )
        dept_map = {row[0]: {"name": row[1], "code": row[2]} for row in dept_rows.all()}

    school_map = {}
    if school_ids:
        school_rows = await session.execute(
            select(School.id, School.name, School.code).where(School.id.in_(school_ids))
        )
        school_map = {row[0]: {"name": row[1], "code": row[2]} for row in school_rows.all()}

    serialized_users = []
    for u in users:
        role_str = str(u.role.value if hasattr(u.role, "value") else u.role).lower()
        school_id = u.school_id

        if "student" in role_str and u.student and u.student.school_id is not None:
            school_id = u.student.school_id

        dept_obj = dept_map.get(u.department_id) if u.department_id is not None else None
        school_obj = school_map.get(school_id) if school_id is not None else None

        if role_str == "staff":
            if school_id is not None:
                role_scope = "school_office"
                role_display = "School Office Staff"
            elif u.department_id is not None:
                role_scope = "department"
                role_display = "Department Staff"
            else:
                role_scope = "unassigned"
                role_display = "Staff"
        elif role_str == "dean":
            role_scope = "school"
            role_display = "School Dean"
        elif role_str == "hod":
            role_scope = "department"
            role_display = "Head of Department"
        elif role_str == "admin":
            role_scope = "global"
            role_display = "Admin"
        elif role_str == "student":
            role_scope = "student"
            role_display = "Student"
        else:
            role_scope = "department"
            role_display = role_str.replace("_", " ").title()

        serialized_users.append(
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "role_scope": role_scope,
                "role_display": role_display,
                "department_id": u.department_id,
                "school_id": school_id,
                "department_name": (u.department.name if u.department else None) or (dept_obj["name"] if dept_obj else None),
                "school_name": (
                    (u.student.school.name if ("student" in role_str and u.student and u.student.school) else None)
                    or (u.school.name if u.school else None)
                    or (school_obj["name"] if school_obj else None)
                ),
                "department_code": (getattr(u.department, "code", None)) or (dept_obj["code"] if dept_obj else None),
                "school_code": (
                    (getattr(u.student.school, "code", None) if ("student" in role_str and u.student and u.student.school) else None)
                    or (getattr(u.school, "code", None) if u.school else None)
                    or (school_obj["code"] if school_obj else None)
                ),
            }
        )

    return {"total": total, "users": serialized_users}


@router.delete("/users/{user_id}", status_code=204)
async def remove_user(
    user_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_admin),
):
    try:
        await delete_user_by_id(session, str(user_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    background_tasks.add_task(
        log_system_event,
        event_type="USER_DELETED",
        actor_id=current_admin.id,
        actor_role=_role_value(current_admin.role),
        resource_type="User",
        resource_id=str(user_id),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        status="SUCCESS",
    )
    return None


@router.put("/users/{user_id}", response_model=UserRead)
async def update_user_endpoint(
    user_id: str,
    data: UserUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_admin),
):
    # Resolve codes → IDs (same logic as register_user)
    final_school_id = data.school_id
    final_dept_id = data.department_id

    if data.school_code:
        school = await _resolve_school_code(session, data.school_code)
        final_school_id = school.id

    if data.department_code:
        dept = await _resolve_dept_code(session, data.department_code)
        final_dept_id = dept.id

    if data.role == UserRole.Dean and not final_school_id:
        raise HTTPException(status_code=400, detail="school_id/code is required for Dean users.")
    if data.role == UserRole.HOD and not final_dept_id:
        raise HTTPException(status_code=400, detail="department_id/code is required for HOD users.")

    # Capture old values for audit log before updating
    old_user = await session.get(User, UUID(user_id))
    old_values = (
        {"role": _role_value(old_user.role), "email": old_user.email}
        if old_user else {}
    )

    try:
        updated_user = await update_user(
            session,
            user_id=user_id,
            name=data.name,
            email=data.email,
            role=data.role,
            department_id=final_dept_id,
            school_id=final_school_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(
        log_system_event,
        event_type="USER_UPDATED",
        actor_id=current_admin.id,
        actor_role=_role_value(current_admin.role),
        resource_type="User",
        resource_id=user_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        old_values=old_values,
        new_values={"role": _role_value(updated_user.role), "email": updated_user.email},
        status="SUCCESS",
    )

    return updated_user


# ---------------------------------------------------------------------------
# CURRENT ADMIN
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserRead)
async def me(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(User)
        .options(selectinload(User.school), selectinload(User.department))
        .where(User.id == current_user.id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# STUDENT MANAGEMENT
# ---------------------------------------------------------------------------

@router.get("/students/{input_id}")
async def admin_get_student_by_id_or_roll(
    input_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    is_uuid = True
    try:
        UUID(input_id)
    except ValueError:
        is_uuid = False

    query = (
        select(Student)
        .options(
            selectinload(Student.school),
            selectinload(Student.programme),
            selectinload(Student.specialization),
        )
    )
    query = (
        query.where(Student.id == input_id)
        if is_uuid
        else query.where(
            or_(
                Student.roll_number == input_id,
                Student.enrollment_number == input_id,
            )
        )
    )

    student = (await session.execute(query)).scalar_one_or_none()
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student not found with identifier: {input_id}",
        )

    latest_app = (await session.execute(
        select(Application)
        .where(Application.student_id == student.id)
        .order_by(Application.created_at.desc())
        .limit(1)
    )).scalars().first()

    # Build response dict — do NOT mutate the tracked ORM object
    app_data = None
    if latest_app:
        app_dict = latest_app.model_dump()
        if latest_app.proof_document_url:
            app_dict["proof_document_url"] = get_signed_url(latest_app.proof_document_url)
        app_data = app_dict

    return {
        "student": student,
        "application": app_data,
        "is_active": latest_app.status in ["pending", "in_progress"] if latest_app else False,
    }


# ---------------------------------------------------------------------------
# GLOBAL SEARCH
# ---------------------------------------------------------------------------

@router.get("/search", response_model=Dict[str, Any])
@limiter.limit("60/minute")
async def admin_global_search(
    request: Request,
    q: str = Query(..., min_length=3),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    term = f"%{q.lower()}%"

    students = (await session.execute(
        select(Student)
        .options(selectinload(Student.school))
        .where(
            or_(
                func.lower(Student.full_name).like(term),
                func.lower(Student.roll_number).like(term),
                func.lower(Student.email).like(term),
                func.lower(Student.enrollment_number).like(term),
            )
        )
        .limit(10)
    )).scalars().all()

    app_results = []
    clean_q = q.strip().upper().replace(" ", "").replace("-", "")

    try:
        uuid_obj = UUID(q)
        app_results = (await session.execute(
            select(Application)
            .options(selectinload(Application.student))
            .where(Application.id == uuid_obj)
            .limit(10)
        )).scalars().all()

    except ValueError:
        # Search by display ID
        by_display = (await session.execute(
            select(Application)
            .options(selectinload(Application.student))
            .where(Application.display_id.ilike(f"%{clean_q}%"))
            .limit(10)
        )).scalars().all()

        app_results = list(by_display)

        # Include applications from matched students (bounded)
        if students:
            student_ids = [s.id for s in students]
            student_apps = (await session.execute(
                select(Application)
                .options(selectinload(Application.student))
                .where(Application.student_id.in_(student_ids))
                .order_by(Application.created_at.desc())
                .limit(10)
            )).scalars().all()

            existing_ids = {app.id for app in app_results}
            for app in student_apps:
                if app.id not in existing_ids:
                    app_results.append(app)

    return {"query": q, "students": students, "applications": app_results}


# ---------------------------------------------------------------------------
# ANALYTICS
# ---------------------------------------------------------------------------

@router.get("/analytics/performance")
async def get_department_performance(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    """
    Returns per-department performance stats using ORM constructs
    instead of raw SQL to stay within SQLAlchemy's type safety guarantees.
    """
    dept_key = func.lower(
        func.coalesce(Department.name, ApplicationStage.verifier_role)
    ).label("dept_key")
    role_key = func.lower(ApplicationStage.verifier_role).label("role_key")
    school_code = School.code.label("school_code")
    dept_code = Department.code.label("dept_code")

    dialect_name = ""
    if session.bind and getattr(session.bind, "dialect", None):
        dialect_name = session.bind.dialect.name

    if dialect_name.startswith("mysql"):
        resolution_hours = (
            func.timestampdiff(
                text("SECOND"),
                ApplicationStage.created_at,
                ApplicationStage.updated_at,
            ) / 3600.0
        )
    else:
        resolution_hours = (
            func.extract(
                "epoch",
                ApplicationStage.updated_at - ApplicationStage.created_at,
            ) / 3600.0
        )

    stmt = (
        select(
            dept_key,
            role_key,
            school_code,
            dept_code,
            func.coalesce(
                func.avg(
                    case(
                        (ApplicationStage.status.in_(["approved", "rejected"]), resolution_hours),
                        else_=None,
                    )
                ),
                0,
            ).label("avg_hours"),
            func.count(
                case((ApplicationStage.status == "pending", 1), else_=None)
            ).label("pending_count"),
            func.count(
                case((ApplicationStage.status == "rejected", 1), else_=None)
            ).label("rejected_count"),
            func.count(
                case((ApplicationStage.status == "approved", 1), else_=None)
            ).label("approved_count"),
            func.count(
                case(
                    (ApplicationStage.status.in_(["approved", "rejected"]), 1),
                    else_=None,
                )
            ).label("total_processed"),
        )
        .outerjoin(Department, ApplicationStage.department_id == Department.id)
        .outerjoin(School, ApplicationStage.school_id == School.id)
        .group_by(dept_key, role_key, school_code, dept_code)
        .order_by(func.count(
            case((ApplicationStage.status == "pending", 1), else_=None)
        ).desc())
    )

    rows = (await session.execute(stmt)).mappings().all()
    grouped: Dict[str, Dict[str, float]] = {}

    for row in rows:
        raw_key = (row.get("dept_key") or "").strip().lower()
        raw_role = (row.get("role_key") or "").strip().lower()
        code = (row.get("school_code") or "").strip().upper()
        department_code = (row.get("dept_code") or "").strip().upper()

        if raw_role == "staff" and raw_key and raw_key != "staff":
            # Department-scoped staff (Library/Hostel/Lab/Accounts/etc) should
            # stay separated by their actual department name.
            dept_name = _dept_display_name(row.get("dept_key"))
        elif raw_role == "hod" and raw_key and raw_key != "hod":
            # Show HOD with short department code (e.g., CSE HOD).
            dept_name = f"{department_code} HOD" if department_code else f"{_dept_display_name(row.get('dept_key'))} HOD"
        elif raw_role == "staff" and code:
            # School-office staff without department routing.
            dept_name = f"{code} Office"
        elif raw_role == "dean" and code:
            dept_name = f"{code} Dean"
        elif raw_role == "staff":
            dept_name = "School Office Staff"
        elif raw_role == "dean":
            dept_name = "School Dean"
        elif raw_role == "hod":
            dept_name = "Head of Department"
        else:
            dept_name = _dept_display_name(row.get("dept_key"))

        avg_hours = float(row.get("avg_hours") or 0)
        pending_count = int(row.get("pending_count") or 0)
        rejected_count = int(row.get("rejected_count") or 0)
        approved_count = int(row.get("approved_count") or 0)
        total_processed = int(row.get("total_processed") or 0)

        if dept_name not in grouped:
            grouped[dept_name] = {
                "weighted_hours_sum": 0.0,
                "pending_count": 0,
                "rejected_count": 0,
                "approved_count": 0,
                "total_processed": 0,
            }

        grouped[dept_name]["weighted_hours_sum"] += avg_hours * total_processed
        grouped[dept_name]["pending_count"] += pending_count
        grouped[dept_name]["rejected_count"] += rejected_count
        grouped[dept_name]["approved_count"] += approved_count
        grouped[dept_name]["total_processed"] += total_processed

    result = []
    for label, data in grouped.items():
        processed = int(data["total_processed"])
        avg_hours = (data["weighted_hours_sum"] / processed) if processed > 0 else 0.0
        result.append(
            {
                "dept_name": label,
                "avg_hours": float(avg_hours),
                "pending_count": int(data["pending_count"]),
                "rejected_count": int(data["rejected_count"]),
                "approved_count": int(data["approved_count"]),
                "total_processed": processed,
            }
        )

    result.sort(key=lambda x: x["pending_count"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# EXPORT REPORT — streaming CSV, no full in-memory load
# ---------------------------------------------------------------------------

@router.get("/reports/export-cleared")
async def export_cleared_students(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    query = (
        select(Application, Student, School, Certificate, Department)
        .join(Student, Application.student_id == Student.id)
        .join(School, Student.school_id == School.id)
        .outerjoin(Department, Student.department_id == Department.id)
        .outerjoin(Certificate, Certificate.application_id == Application.id)
        .where(Application.status == "completed")
        .order_by(School.name, Student.roll_number)
    )

    HEADERS = [
        "Certificate Number", "Roll Number", "Enrollment No", "Student Name",
        "Father's Name", "Gender", "Category",
        "School Code", "School Name",
        "Dept Code", "Department Name",
        "Admission Year", "Mobile", "Email", "Clearance Date",
        "Application Ref (ID)", "System UUID",
    ]

    async def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(HEADERS)
        yield buf.getvalue()

        # Stream rows without loading the full result set into memory
        async for row in await session.stream(query):
            app, student, school, cert, department = row

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                cert.certificate_number if cert else "PENDING",
                student.roll_number,
                student.enrollment_number,
                student.full_name,
                student.father_name,
                student.gender,
                student.category,
                getattr(school, "code", "N/A"),
                school.name,
                department.code if department else "N/A",
                department.name if department else "N/A",
                student.admission_year,
                student.mobile_number,
                student.email,
                app.updated_at.strftime("%Y-%m-%d") if app.updated_at else "N/A",
                app.display_id or "N/A",
                str(app.id),
            ])
            yield buf.getvalue()

    filename = f"cleared_students_{uuid.uuid4().hex[:8]}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )