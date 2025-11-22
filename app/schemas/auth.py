# app/schemas/auth.py

from pydantic import BaseModel, EmailStr
from typing import Optional

from sqlmodel import UUID
from app.models.user import UserRole
from app.schemas.student import StudentRead
from app.schemas.user import UserRead
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

from app.models.user import UserRole
from app.schemas.user import UserRead




# -------------------------------------------------------------------
# LOGIN REQUEST
# -------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# -------------------------------------------------------------------
# REGISTER REQUEST (Super Admin creates any user)
# -------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole   # must match backend enum


# -------------------------------------------------------------------
# TOKEN RESPONSE
# -------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None  # Optional but clean API design


# -------------------------------------------------------------------
# TOKEN + USER DETAILS (Used for login response)
# -------------------------------------------------------------------
class TokenWithUser(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    user: UserRead


# STUDENT LOGIN REQUEST
class StudentLoginRequest(BaseModel):
    identifier: str      # enrollment OR roll number
    password: str

# STUDENT LOGIN RESPONSE
class StudentLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    student_id: UUID
    student: StudentRead

    class Config:
        from_attributes = True
