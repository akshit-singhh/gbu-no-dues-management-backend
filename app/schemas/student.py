# app/schemas/student.py
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from uuid import UUID
from datetime import date, datetime


# ------------------------------------------------------------
# STUDENT REGISTRATION (Public)
# ------------------------------------------------------------
class StudentRegister(BaseModel):
    enrollment_number: str
    roll_number: str
    full_name: str
    mobile_number: str
    email: EmailStr

    password: str
    confirm_password: str

    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("Passwords do not match")
        return v


# ------------------------------------------------------------
# STUDENT UPDATE (Filled during application submission)
# ------------------------------------------------------------
class StudentUpdate(BaseModel):
    full_name: Optional[str]
    father_name: Optional[str]
    mother_name: Optional[str]
    gender: Optional[str]
    category: Optional[str]
    dob: Optional[date]

    permanent_address: Optional[str]
    domicile: Optional[str]
    is_hosteller: Optional[bool]
    hostel_name: Optional[str]
    hostel_room: Optional[str]

    department_id: Optional[int]
    section: Optional[str]
    batch: Optional[str]
    admission_year: Optional[int]
    admission_type: Optional[str]


# ------------------------------------------------------------
# FULL STUDENT READ RESPONSE (Used everywhere in API responses)
# ------------------------------------------------------------
class StudentRead(BaseModel):
    id: UUID

    enrollment_number: str
    roll_number: str
    full_name: str
    mobile_number: str
    email: EmailStr

    father_name: Optional[str]
    mother_name: Optional[str]
    gender: Optional[str]
    category: Optional[str]
    dob: Optional[date]

    permanent_address: Optional[str]
    domicile: Optional[str]
    is_hosteller: Optional[bool]
    hostel_name: Optional[str]
    hostel_room: Optional[str]

    department_id: Optional[int]
    section: Optional[str]
    batch: Optional[str]
    admission_year: Optional[int]
    admission_type: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True
