from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class AuditLogRead(BaseModel):
    id: UUID
    action: str
    actor_id: Optional[UUID] = None
    actor_role: Optional[str] = None
    
    # Added to Response Schema
    actor_name: Optional[str] = None 
    
    application_id: Optional[UUID] = None
    remarks: Optional[str] = None
    details: Dict[str, Any] = {}
    timestamp: datetime

    class Config:
        from_attributes = True

class SystemAuditLogRead(BaseModel):
    id: UUID
    actor_id: Optional[UUID] = None
    actor_role: Optional[str] = None  # ✅ ADDED FIELD
    event_type: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    status: str
    timestamp: datetime

    class Config:
        from_attributes = True