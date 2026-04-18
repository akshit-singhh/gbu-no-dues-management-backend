# app/models/application_stage.py

from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Uuid

# Prevent circular imports
if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.user import User
    from app.models.school import School
    from app.models.department import Department

class ApplicationStage(SQLModel, table=True):
    __tablename__ = "application_stages"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(Uuid(as_uuid=True), primary_key=True)
    )

    application_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    )
    
    # --------------------------------------------------------
    # ROUTING LOGIC
    # --------------------------------------------------------
    # Critical for Dean/School Office stages
    school_id: Optional[int] = Field(
        default=None, 
        sa_column=Column(Integer, ForeignKey("schools.id"), nullable=True)
    )

    # Handles Lab/Department/HOD specific stages
    department_id: Optional[int] = Field(
        default=None, 
        sa_column=Column(Integer, ForeignKey("departments.id"), nullable=True)
    )

    # --------------------------------------------------------
    # STAGE DETAILS
    # --------------------------------------------------------
    verifier_role: str = Field(sa_column=Column(String(50), nullable=False))
    status: str = Field(default="pending", sa_column=Column(String(32), default="pending"))
    
    comments: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    # Link to the User who verified this stage
    verified_by: Optional[UUID] = Field(
        default=None, 
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    )
    
    verified_at: Optional[datetime] = Field(default=None)

    sequence_order: int = Field(default=1, sa_column=Column(Integer, nullable=False))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # --------------------------------------------------------
    # RELATIONSHIPS (Must match back_populates in other models)
    # --------------------------------------------------------
    application: "Application" = Relationship(back_populates="stages")
    
    verifier: Optional["User"] = Relationship(back_populates="verified_stages")

    school: Optional["School"] = Relationship(back_populates="stages")

    department: Optional["Department"] = Relationship(back_populates="stages")