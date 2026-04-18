from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, String, Integer, Text, ForeignKey, Uuid
from uuid import uuid4
from datetime import date, datetime
from typing import Optional, List
import uuid

# Forward references
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.school import School
    from app.models.department import Department
    from app.models.application import Application
    # Added for Academic Hierarchy
    from app.models.academic import Programme, Specialization

class Student(SQLModel, table=True):
    __tablename__ = "students"

    id: uuid.UUID = Field(
        default_factory=uuid4,
        sa_column=Column(Uuid(as_uuid=True), primary_key=True)
    )

    # ----------------------
    # Foreign Keys (Auth)
    # ----------------------
    user_id: uuid.UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    )

    # ----------------------
    # Identity Fields
    # ----------------------
    enrollment_number: str = Field(sa_column=Column(String(40), nullable=False, unique=True))
    roll_number: str = Field(sa_column=Column(String(40), nullable=False, unique=True))
    full_name: str = Field(sa_column=Column(String(150), nullable=False))
    mobile_number: str = Field(sa_column=Column(String(20), nullable=False))
    email: str = Field(sa_column=Column(String(254), nullable=False, unique=True))

    # ----------------------
    # Foreign Keys (Academic)
    # ----------------------
    school_id: int = Field(
        sa_column=Column(Integer, ForeignKey("schools.id"), nullable=False)
    )

    # Link to Academic Department
    department_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("departments.id"), nullable=True)
    )

    # NEW: Programme Link (e.g., B.Tech, M.Tech)
    programme_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("programmes.id"), nullable=True)
    )

    # NEW: Specialization Link (e.g., AI, Data Science)
    specialization_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("specializations.id"), nullable=True)
    )

    # ----------------------
    # Personal Details
    # ----------------------
    father_name: Optional[str] = Field(default=None, sa_column=Column(String(150), nullable=True))
    mother_name: Optional[str] = Field(default=None, sa_column=Column(String(150), nullable=True))
    gender: Optional[str] = Field(default=None, sa_column=Column(String(32), nullable=True))
    category: Optional[str] = Field(default=None, sa_column=Column(String(64), nullable=True))
    dob: Optional[date] = Field(default=None)
    
    permanent_address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    domicile: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    # ----------------------
    # Hostel Info
    # ----------------------
    is_hosteller: Optional[bool] = Field(default=False)
    hostel_name: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    hostel_room: Optional[str] = Field(default=None, sa_column=Column(String(20), nullable=True))

    # ----------------------
    # Academic Details
    # ----------------------
    section: Optional[str] = Field(default=None, sa_column=Column(String(20), nullable=True))
    admission_year: Optional[int] = Field(default=None)
    admission_type: Optional[str] = Field(default=None, sa_column=Column(String(50), nullable=True))

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # ----------------------
    # Relationships
    # ----------------------
    
    # Explicitly specify which foreign key to use (String format)
    user: Optional["User"] = Relationship(
        back_populates="student",
        sa_relationship_kwargs={
            "foreign_keys": "Student.user_id" 
        }
    )
    
    school: Optional["School"] = Relationship(back_populates="students")
    
    # Relationship to access Dept name
    department: Optional["Department"] = Relationship(back_populates="students")

    # NEW: Relationships for Programme & Specialization
    programme: Optional["Programme"] = Relationship()
    specialization: Optional["Specialization"] = Relationship()
    
    applications: List["Application"] = Relationship(back_populates="student")