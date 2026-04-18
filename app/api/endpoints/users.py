# app/api/endpoints/users.py

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session, require_admin
from app.schemas.user import UserRead
from app.models.user import User
from app.models.student import Student
from app.models.department import Department
from app.models.school import School

router = APIRouter(prefix="/api/users", tags=["Users"])

# -------------------------------------------------------------------
# List all users (For convenience, same as /api/admin/users)
# -------------------------------------------------------------------
@router.get("/", response_model=List[UserRead])
async def list_users_standard(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin)
):
    result = await session.execute(
        select(User)
        .options(
            selectinload(User.department),
            selectinload(User.school),
            selectinload(User.student).selectinload(Student.school),
        )
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

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

    response = []
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

        response.append(
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

    return response

# -------------------------------------------------------------------
# Delete a user (For convenience, same as /api/admin/users/{id})
# -------------------------------------------------------------------
@router.delete("/{user_id}")
async def delete_user_standard(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin)
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await session.delete(user)
    await session.commit()
    return {"detail": "User deleted successfully"}
