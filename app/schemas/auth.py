from pydantic import BaseModel, EmailStr, Field, field_validator, ValidationInfo, ConfigDict
from typing import Optional, Any
from uuid import UUID

from app.models.user import UserRole

# -------------------------------------------------------------------
# LOGIN REQUEST
# -------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: str = Field(..., description="Token received from Cloudflare widget")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "password123",
                "turnstile_token": "0.xxxxxxx..."
            }
        }


# -------------------------------------------------------------------
# REGISTER REQUEST (Staff/Admin)
# -------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole
    
    department_code: Optional[str] = None   
    school_code: Optional[str] = None
    
    # Backward compatibility
    department_id: Optional[int] = None 
    school_id: Optional[int] = None

    turnstile_token: Optional[str] = Field(None, description="Token received from Cloudflare widget")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Staff User",
                "email": "staff@example.com",
                "password": "password123",
                "role": "staff",
                "department_code": "LIB",
                "school_code": None,
                "turnstile_token": "0.xxxx..."
            }
        }


# -------------------------------------------------------------------
# TOKEN RESPONSE
# -------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None


# -------------------------------------------------------------------
# TOKEN + USER DETAILS
# -------------------------------------------------------------------
class TokenWithUser(Token):
    user_name: str
    user_role: str
    user_role_scope: Optional[str] = None
    user_role_display: Optional[str] = None
    user_id: UUID
    
    # Extra Context Fields
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    school_id: Optional[int] = None
    school_name: Optional[str] = None
    school_code: Optional[str] = None 
    student_id: Optional[str] = None

# -------------------------------------------------------------------
# STUDENT AUTH SCHEMAS
# -------------------------------------------------------------------

class StudentLoginRequest(BaseModel):
    identifier: str
    password: str
    turnstile_token: str = Field(..., description="Token received from Cloudflare widget")


class StudentWithSchool(BaseModel):
    id: UUID
    full_name: str
    email: str
    roll_number: str
    enrollment_number: str
    mobile_number: Optional[str] = None
    school_id: Optional[int] = None
    school_name: Optional[str] = None
    # ADDED: This fixes the "Dropdown Empty" issue in MyApplications.js
    school_code: Optional[str] = None 
    department_id: Optional[int] = None

    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    admission_year: Optional[int] = None
    gender: Optional[str] = None
    section: Optional[str] = None
    admission_type: Optional[str] = None
    is_hosteller: bool = False
    hostel_name: Optional[str] = None
    hostel_room: Optional[str] = None
    
    #  Also adding these for the "N/A" fix in StudentDashboard
    programme_name: Optional[str] = None
    specialization_name: Optional[str] = None
    
    class Config:
        from_attributes = True
        extra = "allow"


class StudentLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    student_id: UUID
    student: StudentWithSchool 

    class Config:
        from_attributes = True


class StudentRegisterRequest(BaseModel):
    enrollment_number: str
    roll_number: str
    full_name: str
    mobile_number: str = Field(..., min_length=10, max_length=15)
    email: EmailStr
    
    # Code-First Fields
    school_code: str 
    school_id: Optional[int] = None 

    password: str
    confirm_password: Optional[str] = None
    

    turnstile_token: str = Field(..., description="Token received from Cloudflare widget")

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: Optional[str], info: ValidationInfo) -> str:
        password = info.data.get("password")
        if v is None:
            return password if password else ""
        if password and v != password:
            raise ValueError("Passwords do not match")
        return v


# -------------------------------------------------------------------
# FORGOT PASSWORD SCHEMAS
# -------------------------------------------------------------------
class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    turnstile_token: str = Field(..., description="Token received from Cloudflare widget")

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


# -------------------------------------------------------------------
# ADMIN CREATION SCHEMAS
# -------------------------------------------------------------------
class SchoolCreateRequest(BaseModel):
    name: str
    code: str
    requires_lab_clearance: bool = True
    
class DepartmentCreateRequest(BaseModel):
    name: str
    phase_number: int
    code: str
    school_code: Optional[str] = None