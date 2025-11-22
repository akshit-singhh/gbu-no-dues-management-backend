from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class StageActionRequest(BaseModel):
    remarks: Optional[str] = None

class StageActionResponse(BaseModel):
    stage_id: UUID
    application_id: UUID
    department_id: int
    status: str
    remarks: Optional[str]
    reviewer_id: Optional[UUID]

    class Config:
        from_attributes = True
