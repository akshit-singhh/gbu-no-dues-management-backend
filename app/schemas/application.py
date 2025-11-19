from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


# -------------------------------
# Application Create Request
# -------------------------------
class ApplicationCreate(BaseModel):
    student_id: UUID
    remarks: Optional[str] = None


# -------------------------------
# Application Response Schema
# -------------------------------
class ApplicationRead(BaseModel):
    id: UUID
    student_id: UUID
    office_verifier_id: Optional[UUID]
    status: str
    current_department_id: Optional[int]
    remarks: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
