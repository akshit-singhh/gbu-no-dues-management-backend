# app/models/user.py

from enum import Enum
from typing import Optional, TYPE_CHECKING, List
from uuid import UUID, uuid4
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# Prevent circular imports
if TYPE_CHECKING:
    from app.models.student import Student
    from app.models.application_stage import ApplicationStage
    from app.models.school import School
    from app.models.department import Department

class UserRole(str, Enum):
    # ------------------------------------------------------------
    # SYSTEM ROLES
    # ------------------------------------------------------------
    Admin = "admin"              
    Student = "student"          
    
    # Generic Staff Role (Used for Library, Accounts, School Office, etc.)
    Staff = "staff"

    # ------------------------------------------------------------
    # APPROVAL AUTHORITY ROLES
    # ------------------------------------------------------------
    Dean = "dean"                # School Dean
    HOD = "hod"                  # Academic Head (Flow B)

    # Legacy Roles
    Library = "library"          
    Hostel = "hostel"            
    Lab = "lab"                  
    Account = "account"          
    Sports = "sports"            
    CRC = "crc"                  

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    name: str = Field(sa_column=Column(String, nullable=False))
    email: str = Field(sa_column=Column(String, unique=True, index=True, nullable=False))
    password_hash: str = Field(sa_column=Column(String, nullable=False))
    
    role: UserRole = Field(sa_column=Column(String, default=UserRole.Student.value))
    
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # --------------------------------------------------------
    # FOREIGN KEYS
    # --------------------------------------------------------
    # Note: We keep student_id for quick lookup, but the Relationship 
    # below is the source of truth for the link.
    student_id: Optional[UUID] = Field(default=None, foreign_key="students.id")

    # Routing Foreign Keys (For Deans/Staff)
    school_id: Optional[int] = Field(default=None, foreign_key="schools.id")
    department_id: Optional[int] = Field(default=None, foreign_key="departments.id")

    # --------------------------------------------------------
    #  PASSWORD RESET
    # --------------------------------------------------------
    otp_code: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    otp_expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))

    # --------------------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------------------
    
    #  Explicitly specify foreign_keys to resolve ambiguity
    student: Optional["Student"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "foreign_keys": "Student.user_id",
            "cascade": "all, delete-orphan"
        }
    )
    
    # Relationship to stages verified by this user
    verified_stages: List["ApplicationStage"] = Relationship(back_populates="verifier")

    # School Link (For Deans)
    school: Optional["School"] = Relationship(back_populates="users")

    # Department Link (For Staff/HODs)
    department: Optional["Department"] = Relationship(back_populates="users")