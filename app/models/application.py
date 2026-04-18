# app/models/application.py

from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID, uuid4
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, String, Text, Uuid

# Use TYPE_CHECKING to avoid circular import errors at runtime
if TYPE_CHECKING:
    from app.models.student import Student
    from app.models.application_stage import ApplicationStage

class ApplicationStatus(str, Enum):
    PENDING = "pending"         # Just created
    IN_PROGRESS = "in_progress" # Being verified by departments
    REJECTED = "rejected"       # Returned to student (Paused)
    COMPLETED = "completed"     # All stages done (Certificate issued)
    APPROVED = "approved"       # (Rarely used for main app)

# ----------------------------------------------------------------
# 1. The Main Application Table
# ----------------------------------------------------------------
class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(Uuid(as_uuid=True), primary_key=True)
    )

    # Readable ID (e.g., ND235ICS066A7)
    display_id: Optional[str] = Field(
        default=None, 
        sa_column=Column(String(32), unique=True, index=True)
    )

    student_id: UUID = Field(foreign_key="students.id", nullable=False)
    
    status: str = Field(default=ApplicationStatus.PENDING.value, sa_column=Column(String(32), nullable=False))
    
    # Official remarks from Approvers (e.g. "Rejected due to missing fee")
    remarks: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    # ADDED To store the Student's reply when resubmitting
    student_remarks: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    # Stores the internal path or Public URL for the uploaded PDF
    proof_document_url: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    current_stage_order: int = Field(default=1)
    is_completed: bool = Field(default=False)
    
    # Legacy field (kept for safety)
    current_department_id: Optional[int] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Automatically updates timestamp on modification
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    )

    # Relationships
    student: "Student" = Relationship(back_populates="applications")
    
    # Forward reference to ApplicationStage
    stages: List["ApplicationStage"] = Relationship(back_populates="application")