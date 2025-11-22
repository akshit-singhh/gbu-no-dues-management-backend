# app/schemas/application.py

from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import date, datetime


# ============================================================
# STUDENT → Allowed fields during application submission
# ============================================================
class StudentApplicationUpdate(BaseModel):
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

    class Config:
        from_attributes = True



# ============================================================
# APPLICATION CREATE SCHEMA  (Student submits only details)
# ============================================================
class ApplicationCreate(BaseModel):
    student_update: StudentApplicationUpdate  # required → students must send details


# ============================================================
# APPLICATION READ (Admin / Status)
# ============================================================
class ApplicationRead(BaseModel):
    id: UUID
    student_id: UUID
    office_verifier_id: Optional[UUID]
    status: str
    remarks: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

