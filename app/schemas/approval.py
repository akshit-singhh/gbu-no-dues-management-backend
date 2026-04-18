# app/schemas/approval.py

from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional
from datetime import datetime

# ----------------------------------------------------------------
# REQUEST: Standard Action (Approve/Reject by User)
# ----------------------------------------------------------------
class StageActionRequest(BaseModel):
    remarks: Optional[str] = None


# ----------------------------------------------------------------
# REQUEST: Admin Override (Force Action)
# ----------------------------------------------------------------
class AdminOverrideRequest(BaseModel):
    stage_id: UUID
    action: str  # Must be "approve" or "reject"
    remarks: Optional[str] = "Admin Override"


# ----------------------------------------------------------------
# RESPONSE (Output to User)
# ----------------------------------------------------------------
class StageActionResponse(BaseModel):
    id: UUID
    application_id: UUID
    
    # School ID (For Dean Stages)
    school_id: Optional[int] = None

    # (Used for HOD, Library, Hostel, etc.)
    department_id: Optional[int] = None
    
    verifier_role: str
    status: str
    
    comments: Optional[str] = None
    
    verified_by: Optional[UUID] = None
    
    verified_at: Optional[datetime] = None
    
    sequence_order: int
    created_at: datetime
    updated_at: datetime

    # Pydantic V2 Configuration
    model_config = ConfigDict(from_attributes=True)