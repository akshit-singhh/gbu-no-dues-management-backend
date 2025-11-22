from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import uuid

from app.models.user import User, UserRole
from app.models.student import Student
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.schemas.auth import TokenWithUser
from app.schemas.user import UserRead
from app.schemas.auth_student import StudentLoginResponse


# =====================================================================
# FETCH USER BY EMAIL
# =====================================================================
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# =====================================================================
# FETCH USER BY ID (Used by JWT)
# =====================================================================
async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# =====================================================================
# CREATE USER
# =====================================================================
async def create_user(
    session: AsyncSession,
    name: str,
    email: str,
    password: str,
    role: UserRole = UserRole.Office,
    department_id: int | None = None,
    student_id: uuid.UUID | None = None,
) -> User:

    role_value = role.value if isinstance(role, UserRole) else role

    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role_value,                 # ALWAYS STRING
        department_id=department_id,
        student_id=student_id,
    )

    session.add(user)

    try:
        await session.commit()
        await session.refresh(user)
        return user

    except IntegrityError:
        await session.rollback()
        raise ValueError("User with this email already exists")


# =====================================================================
# AUTHENTICATE STAFF/ADMIN
# =====================================================================
async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> User | None:

    user = await get_user_by_email(session, email)
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


# =====================================================================
# CREATE LOGIN RESPONSE
# =====================================================================
def create_login_response(user: User) -> TokenWithUser:

    # Guarantee clean lowercase string role
    role_str = (
        user.role.value.lower()
        if isinstance(user.role, UserRole)
        else str(user.role).lower()
    )

    token = create_access_token(
        subject=str(user.id),
        data={"role": role_str}
    )

    return TokenWithUser(
        access_token=token,
        user=UserRead.from_orm(user),
        expires_in=3600
    )

# =====================================================================
# AUTHENTICATE STUDENT
# =====================================================================
async def authenticate_student(
    session: AsyncSession,
    identifier: str,
    password: str
) -> StudentLoginResponse | None:

    print("\n===== STUDENT LOGIN DEBUG =====")
    identifier = identifier.strip()
    print("Identifier Received:", identifier)

    # 1) FIND STUDENT
    result = await session.execute(
        select(Student).where(
            (Student.enrollment_number.ilike(identifier)) |
            (Student.roll_number.ilike(identifier))
        )
    )
    student = result.scalar_one_or_none()

    print("STEP 1: Student found =", student is not None)
    if student:
        print("  → Student ID:", student.id)
        print("  → Enrollment:", student.enrollment_number)
        print("  → Roll:", student.roll_number)
    else:
        print("  → NO STUDENT MATCHED in DB")
        return None

    # 2) FIND USER LINKED TO STUDENT
    result = await session.execute(
        select(User).where(User.student_id == student.id)
    )
    user = result.scalar_one_or_none()

    print("STEP 2: User found =", user is not None)
    if user:
        print("  → User ID:", user.id)
        print("  → User email:", user.email)
        print("  → Stored role:", user.role)
    else:
        print("  → NO USER LINKED WITH student_id =", student.id)
        return None

    # 3) ROLE CHECK
    # 3) Normalize & validate role
    if isinstance(user.role, UserRole):
        role_str = user.role.value.lower()
    else:
        role_str = str(user.role).lower()

    if role_str != "student":
        print("  → ROLE MISMATCH (expected 'student'), got:", role_str)
        return None


    # 4) PASSWORD CHECK
    print("STEP 4: Verifying password…")
    password_ok = verify_password(password, user.password_hash)
    print("  → Password match =", password_ok)

    if not password_ok:
        print("  → PASSWORD MISMATCH")
        return None

    print("STEP 5: PASSWORD OK → Creating token...")

    token = create_access_token(
        subject=str(user.id),
        data={"role": "student"}
    )

    print("===== LOGIN SUCCESS =====")

    return StudentLoginResponse(
        access_token=token,
        user_id=user.id,
        student_id=student.id,
        student=student,
    )


# =====================================================================
# LIST USERS
# =====================================================================
async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return result.scalars().all()


# =====================================================================
# DELETE USER
# =====================================================================
async def delete_user_by_id(session: AsyncSession, user_id: str) -> None:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    await session.delete(user)
    await session.commit()


# =====================================================================
# UPDATE USER
# =====================================================================
async def update_user(
    session: AsyncSession,
    user_id: str,
    name: str | None = None,
    email: str | None = None,
    role: UserRole | str | None = None,
    department_id: int | None = None,
) -> User:

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    if email and email != user.email:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise ValueError("Email already in use")
        user.email = email

    if name:
        user.name = name

    if role:
        user.role = role.value if isinstance(role, UserRole) else role

    if department_id is not None:
        user.department_id = department_id

    try:
        await session.commit()
        await session.refresh(user)
        return user

    except IntegrityError:
        await session.rollback()
        raise ValueError("Failed to update user")
