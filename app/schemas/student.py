from pydantic import BaseModel, EmailStr, field_validator, ValidationInfo, ConfigDict, model_validator, Field
from typing import Optional, Any
from uuid import UUID
from datetime import date, datetime
from sqlmodel import select
from sqlalchemy.orm import selectinload
from app.models.student import Student
# ------------------------------------------------------------
# STUDENT REGISTRATION (Code-First Approach)
# ------------------------------------------------------------
class StudentRegister(BaseModel):
    enrollment_number: str
    roll_number: str
    full_name: str
    mobile_number: str = Field(..., min_length=10, max_length=15)
    email: EmailStr
    
    # School is required for initial registration to route them correctly
    school_code: str 
    school_id: Optional[int] = None # Optional fallback

    password: str
    confirm_password: Optional[str] = None
    
    # ✅ CHANGE: Replaced old Captcha with Cloudflare Turnstile
    turnstile_token: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: Optional[str], info: ValidationInfo) -> str:
        password = info.data.get("password")
        if v is None:
            return password if password else ""
        if password and v != password:
            raise ValueError("Passwords do not match")
        return v


# ------------------------------------------------------------
# STUDENT UPDATE (For PATCH /api/students/me)
# ------------------------------------------------------------
class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[EmailStr] = None
    
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    dob: Optional[date] = None

    permanent_address: Optional[str] = None
    domicile: Optional[str] = None
    
    # Hostel Details
    is_hosteller: Optional[bool] = None
    hostel_name: Optional[str] = None
    hostel_room: Optional[str] = None

    # Academic Details
    school_id: Optional[int] = None
    
    # Allow updating Academic Dept via Code (Robust)
    department_code: Optional[str] = None 
    department_id: Optional[int] = None 
    
    # ✅ NEW: Allow updating Programme & Specialization
    programme_code: Optional[str] = None
    specialization_code: Optional[str] = None
    
    section: Optional[str] = None
    admission_year: Optional[int] = None
    admission_type: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------
# FULL STUDENT READ RESPONSE
# ------------------------------------------------------------
class StudentRead(BaseModel):
    id: UUID

    enrollment_number: str
    roll_number: str
    full_name: str
    mobile_number: str
    email: EmailStr

    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    dob: Optional[date] = None

    permanent_address: Optional[str] = None
    domicile: Optional[str] = None
    is_hosteller: Optional[bool] = None
    hostel_name: Optional[str] = None
    hostel_room: Optional[str] = None

    # IDs
    school_id: Optional[int] = None
    department_id: Optional[int] = None
    programme_id: Optional[int] = None
    specialization_id: Optional[int] = None

    # Names & Codes (Populated via Validator for UI convenience)
    school_name: Optional[str] = None
    school_code: Optional[str] = None
    
    department_name: Optional[str] = None
    department_code: Optional[str] = None

    # ✅ NEW: Display Programme & Specialization info
    programme_name: Optional[str] = None
    programme_code: Optional[str] = None
    
    specialization_name: Optional[str] = None
    specialization_code: Optional[str] = None

    section: Optional[str] = None
    admission_year: Optional[int] = None
    admission_type: Optional[str] = None

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    # Validator to extract Names & Codes from Relationships
    @model_validator(mode='before')
    @classmethod
    def flatten_details(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        
        # Helper to safely get attribute from object or dict
        def get_attr(obj, attr):
            return getattr(obj, attr, None) if obj else None

        # If it's a SQLModel/ORM object
        return {
            "id": data.id,
            "enrollment_number": data.enrollment_number,
            "roll_number": data.roll_number,
            "full_name": data.full_name,
            "mobile_number": data.mobile_number,
            "email": data.email,
            "father_name": data.father_name,
            "mother_name": data.mother_name,
            "gender": data.gender,
            "category": data.category,
            "dob": data.dob,
            "permanent_address": data.permanent_address,
            "domicile": data.domicile,
            "is_hosteller": data.is_hosteller,
            "hostel_name": data.hostel_name,
            "hostel_room": data.hostel_room,
            
            # --- School ---
            "school_id": data.school_id,
            "school_name": get_attr(data.school, "name"),
            "school_code": get_attr(data.school, "code"),
            
            # --- Department ---
            "department_id": data.department_id,
            "department_name": get_attr(data.department, "name"),
            "department_code": get_attr(data.department, "code"),

            # --- ✅ Programme ---
            "programme_id": data.programme_id,
            "programme_name": get_attr(data.programme, "name"),
            "programme_code": get_attr(data.programme, "code"),

            # --- ✅ Specialization ---
            "specialization_id": data.specialization_id,
            "specialization_name": get_attr(data.specialization, "name"),
            "specialization_code": get_attr(data.specialization, "code"),
            
            "section": data.section,
            "admission_year": data.admission_year,
            "admission_type": data.admission_type,
            "created_at": data.created_at
        }