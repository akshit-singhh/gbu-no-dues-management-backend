# app/schemas/auth.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from app.models.user import UserRole
from app.schemas.user import UserRead   # <-- IMPORTANT


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
    user: UserRead            # <-- Typed, strict, clean
