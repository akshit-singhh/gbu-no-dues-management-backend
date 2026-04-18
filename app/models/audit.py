#app/models/audit.py

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, Text, JSON
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    application_id: Optional[UUID] = Field(default=None, foreign_key="applications.id")
    actor_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    actor_role: Optional[str] = Field(default=None, sa_column=Column(String(50), nullable=True))
    
    # 1. NEW FIELD: Actor Name (Snapshot)
    actor_name: Optional[str] = Field(default=None, sa_column=Column(String(150), nullable=True)) 
    
    action: str = Field(sa_column=Column(String(80), nullable=False))
    remarks: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    
    # Stores {"student_roll": "...", "stage": "..."}
    details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False)) 
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)