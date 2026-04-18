import string
from sqlmodel import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
import uuid
import random
from datetime import datetime, timedelta

from loguru import logger 

from app.models.application import Application
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.department import Department
from app.models.school import School
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
)
from app.schemas.auth import TokenWithUser, StudentLoginResponse
# from app.schemas.student import StudentRegister # Removed: Service shouldn't depend on API schemas if possible
from app.core.config import settings

# ============================================================================
# FETCH USER BY EMAIL
# ============================================================================
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email).options(selectinload(User.student))
    result = await session.execute(statement)
    return result.scalar_one_or_none()

async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    try:
        uuid_obj = uuid.UUID(str(user_id))
    except ValueError:
        return None
        
    statement = select(User).where(User.id == uuid_obj).options(selectinload(User.student))
    result = await session.execute(statement)
    return result.scalar_one_or_none()

# ============================================================================
# CREATE STUDENT (Renamed & Updated to match Endpoint)
# ============================================================================
async def create_student(
    session: AsyncSession, 
    enrollment_number: str,
    roll_number: str,
    full_name: str,
    email: str,
    mobile_number: str,
    password: str,
    school_code: str,
    school_id: int | None = None
) -> Student:
    """
    Creates a User account first, then creates a Student profile linked to it.
    Resolves School Code (e.g., 'SOICT') to School ID.
    """
    # 1. Check if Email Exists (User Table)
    existing_user = await get_user_by_email(session, email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # 2. Check Enrollment/Roll No (Student Table)
    stmt = select(Student).where(
        or_(
            Student.enrollment_number == enrollment_number,
            Student.roll_number == roll_number
        )
    )
    result = await session.execute(stmt)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enrollment or Roll Number already registered"
        )

    # 3. RESOLVE SCHOOL CODE -> ID
    final_school_id = school_id # Fallback if ID is passed directly
    
    # Check if school_code is provided (Preferred)
    if school_code:
        stmt = select(School).where(School.code == school_code.strip().upper())
        school_res = await session.execute(stmt)
        school = school_res.scalar_one_or_none()
        
        if not school:
             raise HTTPException(400, f"Invalid School Code: {school_code}")
        final_school_id = school.id

    if not final_school_id:
         raise HTTPException(400, "School selection is required.")

    # 4. Generate IDs explicitly
    new_user_id = uuid.uuid4()
    new_student_id = uuid.uuid4()

    # 5. STEP 1: Create User
    new_user = User(
        id=new_user_id,
        name=full_name,
        email=email,
        password_hash=get_password_hash(password),
        role=UserRole.Student,
        school_id=final_school_id, # Link User to School
        student_id=None,           # Leave None initially to avoid FK error
        is_active=True
    )
    session.add(new_user)
    
    # 6. STEP 2: Create Student (Linked to User)
    new_student = Student(
        id=new_student_id,
        user_id=new_user_id, # Backward Link
        school_id=final_school_id,
        enrollment_number=enrollment_number,
        roll_number=roll_number,
        full_name=full_name,
        mobile_number=mobile_number,
        email=email
    )
    session.add(new_student)

    try:
        # Flush to generate IDs in DB transaction
        await session.flush()

        # 7. STEP 3: Update User to link to Student
        new_user.student_id = new_student_id
        session.add(new_user) 

        # 8. Commit
        await session.commit()
        await session.refresh(new_student)
        return new_student

    except Exception as e:
        await session.rollback()
        logger.error(f"Registration DB Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during registration: {str(e)}"
        )


# ============================================================================
# CREATE USER (General Admin Use - Supports Flow B)
# ============================================================================
async def create_user(
    session: AsyncSession,
    name: str,
    email: str,
    password: str,
    role: UserRole,
    department_id: int | None = None, # Passed as ID (Resolved by Endpoint)
    student_id: uuid.UUID | None = None,
    school_id: int | None = None,     # Passed as ID (Resolved by Endpoint)
) -> User:
    """
    Creates a user. 
    Note: The calling endpoint (auth.py) is responsible for resolving 
    Codes (e.g., 'ACC', 'SOICT') into the IDs passed here.
    """

    user_data = {
        "id": uuid.uuid4(),
        "name": name,
        "email": email,
        "password_hash": get_password_hash(password),
        "role": role,
        "student_id": student_id,
        "department_id": department_id,
        "school_id": school_id,
        "is_active": True
    }

    user = User(**user_data)
    session.add(user)

    try:
        await session.commit()
        
        # Refresh with Eager Load for response consistency
        stmt = (
            select(User)
            .options(
                selectinload(User.school),
                selectinload(User.department),
                selectinload(User.student)
            )
            .where(User.id == user.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    except IntegrityError:
        await session.rollback()
        raise ValueError("User with this email already exists")


# ============================================================================
# AUTHENTICATE USER (Admin / Staff)
# ============================================================================
async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None
    
    if hasattr(user, "is_active") and not user.is_active:
        return None

    return user


# ============================================================================
# AUTHENTICATE STUDENT LOGIN (Roll No / Enrollment No only)
# ============================================================================
async def authenticate_student(
    session: AsyncSession,
    identifier: str,
    password: str
) -> StudentLoginResponse | None:

    identifier = identifier.strip()

    # 1. Fetch Student 
    query = (
        select(Student)
        .options(selectinload(Student.school))
        .where(
            or_(
                Student.enrollment_number.ilike(identifier),
                Student.roll_number.ilike(identifier)
            )
        )
    )
    result = await session.execute(query)
    students = result.scalars().all()
    
    if not students:
        return None
        
    # Self-Healing Logic for Duplicates
    if len(students) > 1:
        logger.warning(f"Duplicate student records found for: {identifier}. Using most recent.")
        student = sorted(students, key=lambda s: s.created_at, reverse=True)[0]
    else:
        student = students[0]

    # 2. Fetch Linked User
    result = await session.execute(
        select(User)
        .where(User.student_id == student.id)
        .options(selectinload(User.student))
    )
    user = result.scalars().first()
    
    if not user:
        return None

    # Verify Role
    user_role_val = user.role.value if hasattr(user.role, "value") else user.role
    if str(user_role_val) != UserRole.Student.value:
        return None

    # Verify Password
    if not verify_password(password, user.password_hash):
        return None

    # Generate Token
    token = create_access_token(
        subject=str(user.id),
        data={
            "role": "student",
            "student_id": str(student.id),
            "school_id": student.school_id
        }
    )

    # ---------------------------------------------------------
    # EXPLICIT DATA MAPPING
    # ---------------------------------------------------------
    # model_dump() only converts columns on the Student table.
    # We must manually inject fields from the joined School table.
    student_dict = student.model_dump()
    
    if student.school:
        student_dict["school_name"] = student.school.name
        student_dict["school_code"] = student.school.code  # Pulling 'SOICT'
    else:
        student_dict["school_name"] = "Unknown School"
        student_dict["school_code"] = "N/A"

    # Return the fully mapped response
    return StudentLoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        student_id=student.id,
        student=student_dict,
    )


# ============================================================================
# CREATE LOGIN RESPONSE
# ============================================================================
async def create_login_response(user: User, session: AsyncSession) -> TokenWithUser:
    role_str = str(user.role.value if hasattr(user.role, "value") else user.role).lower()

    user_dept_id = getattr(user, "department_id", None)
    user_school_id = getattr(user, "school_id", None)
    
    if user.student and user.student.school_id:
        user_school_id = user.student.school_id

    # Role context for frontend display (does not alter authorization role).
    user_role_scope = None
    user_role_display = None
    if role_str == "staff":
        if user_school_id is not None:
            user_role_scope = "school_office"
            user_role_display = "School Office Staff"
        elif user_dept_id is not None:
            user_role_scope = "department"
            user_role_display = "Department Staff"
        else:
            user_role_scope = "unassigned"
            user_role_display = "Staff"
    elif role_str == "dean":
        user_role_scope = "school"
        user_role_display = "School Dean"
    elif role_str == "hod":
        user_role_scope = "department"
        user_role_display = "Head of Department"
    elif role_str == "admin":
        user_role_scope = "global"
        user_role_display = "Admin"
    elif role_str == "student":
        user_role_scope = "student"
        user_role_display = "Student"
    else:
        user_role_scope = "department"
        user_role_display = role_str.replace("_", " ").title()

    # 1. Fetch Department Info (Safe Code Access)
    department_name = None
    department_code = None
    if user_dept_id:
        try:
            result = await session.execute(select(Department).where(Department.id == user_dept_id))
            dept = result.scalar_one_or_none()
            if dept:
                department_name = dept.name
                department_code = dept.code
        except:
            pass

    # 2. Fetch School Info (Safe Code Access)
    school_name = None
    school_code = None
    if user_school_id:
        try:
            result = await session.execute(select(School).where(School.id == user_school_id))
            school = result.scalar_one_or_none()
            if school:
                school_name = school.name
                school_code = school.code
        except:
            pass

    # 3. Create Token Claims
    token_data = {
        "role": role_str,
        "role_scope": user_role_scope,
        "department_id": user_dept_id,
        "department_code": department_code, # Useful for frontend logic
        "school_id": user_school_id,
        "school_code": school_code,         # Useful for frontend logic
    }
    
    if user.student_id:
        token_data["student_id"] = str(user.student_id)

    token = create_access_token(
        subject=str(user.id),
        data=token_data,
    )

    return TokenWithUser(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_name=user.name,
        user_role=role_str,
        user_role_scope=user_role_scope,
        user_role_display=user_role_display,
        user_id=user.id,
        
        department_id=user_dept_id,
        department_name=department_name,
        school_id=user_school_id,
        school_name=school_name
    )


# ============================================================================
# PASSWORD RESET UTILS (Standard)
# ============================================================================
async def request_password_reset(session: AsyncSession, email: str):
    """
    Generates a 6-digit OTP and sets expiry to 5 minutes from now.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User with this email not found")

    # Generate 6-digit OTP
    otp = ''.join(random.choices(string.digits, k=6))
    
    # Set OTP and Expiry (Now + 5 minutes)
    user.otp_code = otp
    user.otp_expires_at = datetime.utcnow() + timedelta(minutes=5)
    
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    return otp, user

async def verify_reset_otp(session: AsyncSession, email: str, otp: str) -> bool:
    """
    Verifies the OTP and checks if it is expired.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.otp_code or not user.otp_expires_at:
        return False

    # Check 1: Does OTP Match?
    if user.otp_code != otp:
        return False

    # Check 2: Is it Expired?
    if datetime.utcnow() > user.otp_expires_at:
        return False

    return True

async def finalize_password_reset(session: AsyncSession, email: str, otp: str, new_password: str):
    """
    Resets the password if OTP is valid.
    """
    # Verify again just to be safe
    is_valid = await verify_reset_otp(session, email, otp)
    if not is_valid:
        raise ValueError("Invalid or expired OTP")

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one()

    # Update Password and Clear OTP
    user.password_hash = get_password_hash(new_password)
    user.otp_code = None
    user.otp_expires_at = None
    
    session.add(user)
    await session.commit()


# ============================================================================
# LIST USERS
# ============================================================================
async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return result.scalars().all()


# ============================================================================
# DELETE USER
# ============================================================================
async def delete_user_by_id(session: AsyncSession, user_id: str) -> None:
    try:
        uuid_obj = uuid.UUID(str(user_id))
    except ValueError:
        raise ValueError("Invalid User ID")

    # 1. Fetch the User
    result = await session.execute(select(User).where(User.id == uuid_obj))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    # 2. Check if the user has a linked Student profile
    student_result = await session.execute(select(Student).where(Student.user_id == user.id))
    student = student_result.scalar_one_or_none()

    if student:
        # 3. Check if this student has ANY applications
        app_result = await session.execute(select(Application).where(Application.student_id == student.id))
        existing_app = app_result.scalars().first()

        # 4. BLOCK DELETION if an application exists
        if existing_app:
            raise ValueError("Cannot delete this user because they have submitted an application. Please reject or archive the application first.")
        
        # ✅ THE FIX: Break the two-way link before deleting!
        user.student_id = None
        session.add(user)
        await session.flush() # Forces the database to update the User right now
        
        # Now it is safe to delete the student profile
        await session.delete(student)

    # 5. Finally, delete the User
    await session.delete(user)
    await session.commit()


# ============================================================================
# UPDATE USER
# ============================================================================
async def update_user(
    session: AsyncSession,
    user_id: str,
    name: str | None = None,
    email: str | None = None,
    role: UserRole | None = None,
    department_id: int | None = None,
    school_id: int | None = None,
) -> User:

    try:
        uuid_obj = uuid.UUID(str(user_id))
    except ValueError:
        raise ValueError("Invalid User ID")

    # 1. Fetch User
    result = await session.execute(select(User).where(User.id == uuid_obj))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    # 2. Update Email (Check Duplicates)
    if email and email != user.email:
        dup = await session.execute(select(User).where(User.email == email))
        if dup.scalar_one_or_none():
            raise ValueError("Email already in use")
        user.email = email

    if name: user.name = name
    if role: user.role = role

    # 3. Handle Foreign Keys (0 -> None)
    if department_id is not None:
        if department_id == 0:
            user.department_id = None
        else:
            user.department_id = department_id

    if school_id is not None:
        if school_id == 0:
            user.school_id = None
        else:
            user.school_id = school_id

    # 4. Save & Return
    try:
        await session.commit()
        
        stmt = (
            select(User)
            .options(
                selectinload(User.school),
                selectinload(User.department),
                selectinload(User.student).selectinload(Student.school)
            )
            .where(User.id == user.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    except IntegrityError as e:
        await session.rollback()
        print(f"Update User Error: {str(e)}") 
        if "foreign key constraint" in str(e).lower():
            raise ValueError("Invalid School ID or Department ID provided.")
        raise ValueError("Failed to update user (Database Integrity Error)")