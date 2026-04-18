# app/models/system_audit.py

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, JSON
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

class SystemAuditLog(SQLModel, table=True):
    __tablename__ = "system_audit_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Who did it (can be null if it's an anonymous action, like a failed login attempt)
    actor_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    
    #NEW: What was their role at the time of the action?
    actor_role: Optional[str] = Field(default=None, sa_column=Column(String(50), nullable=True))
    
    # What kind of event (e.g., "USER_LOGIN", "ROLE_CHANGED", "SETTINGS_UPDATED")
    event_type: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    
    # What resource was affected (e.g., "User", "Department", "SystemConfig")
    resource_type: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    resource_id: Optional[str] = Field(default=None, sa_column=Column(String(64), nullable=True))
    
    # Security context
    ip_address: Optional[str] = Field(default=None, sa_column=Column(String(45), nullable=True))
    user_agent: Optional[str] = Field(default=None, sa_column=Column(String(512), nullable=True))
    
    # The actual changes made as structured JSON payloads
    old_values: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    new_values: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    
    # Outcome (e.g., "SUCCESS", "FAILURE")
    status: str = Field(default="SUCCESS", sa_column=Column(String(20), nullable=False))
    
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)