from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
# 
class ApprovalSummary(BaseModel):
    application_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    student_id: UUID
    student_name: str
    roll_number: str
    enrollment_number: str

    current_department_id: Optional[int]
    current_department_name: Optional[str]

    office_verifier_id: Optional[UUID]
    office_verifier_name: Optional[str]

    class Config:
        from_attributes = True
