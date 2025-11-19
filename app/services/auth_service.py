# app/services/auth_service.py

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import uuid

from app.models.user import User, UserRole
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.schemas.auth import TokenWithUser
from app.schemas.user import UserRead


# -------------------------------------------------------------------
# FETCH USER BY EMAIL
# -------------------------------------------------------------------
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# -------------------------------------------------------------------
# CREATE USER
# -------------------------------------------------------------------
async def create_user(
    session: AsyncSession,
    name: str,
    email: str,
    password: str,
    role: UserRole = UserRole.staff,
    department_id: int | None = None,
) -> User:
    """Create a new user safely."""
    
    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role.value if isinstance(role, UserRole) else role,
        department_id=department_id,
    )

    session.add(user)

    try:
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError:
        await session.rollback()
        raise ValueError("User with this email already exists")


# -------------------------------------------------------------------
# AUTHENTICATE USER (LOGIN HELPER)
# -------------------------------------------------------------------
async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


# -------------------------------------------------------------------
# CREATE TOKEN + USER RESPONSE (LOGIN OUTPUT)
# -------------------------------------------------------------------
def create_login_response(user: User) -> TokenWithUser:
    """
    Create a full login response:
    - JWT access token
    - Token type
    - User details
    """
    token = create_access_token(
        subject=str(user.id),
        data={"role": user.role}
    )

    return TokenWithUser(
        access_token=token,
        user=UserRead.from_orm(user),
        expires_in=3600   # optional — set based on your JWT config
    )


# -------------------------------------------------------------------
# LIST USERS
# -------------------------------------------------------------------
async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return result.scalars().all()


# -------------------------------------------------------------------
# DELETE USER
# -------------------------------------------------------------------
async def delete_user_by_id(session: AsyncSession, user_id: str) -> None:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    await session.delete(user)
    await session.commit()


# -------------------------------------------------------------------
# UPDATE USER
# -------------------------------------------------------------------
async def update_user(
    session: AsyncSession,
    user_id: str,
    name: str | None = None,
    email: str | None = None,
    role: UserRole | str | None = None,
    department_id: int | None = None,
) -> User:

    # Fetch user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    # Email change validation
    if email and email != user.email:
        existing_user = await session.execute(select(User).where(User.email == email))
        if existing_user.scalar_one_or_none():
            raise ValueError("Email already in use")
        user.email = email

    # Update fields
    if name:
        user.name = name

    if role:
        user.role = role.value if isinstance(role, UserRole) else role

    if department_id is not None:
        user.department_id = department_id

    # Save
    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise ValueError("Database constraint error while updating user")

    return user


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
