from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Integer, String

# Prevent circular imports
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.student import Student
    from app.models.application_stage import ApplicationStage
    from app.models.school import School
    from app.models.academic import Programme

class Department(SQLModel, table=True):
    __tablename__ = "departments"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True)
    )

    name: str = Field(
        sa_column=Column(String(128), nullable=False, unique=True)
    )

    # Stable Identifier (e.g., 'CSE', 'LIB', 'ACC')
    code: str = Field(
        sa_column=Column(String(20), nullable=False, unique=True, index=True)
    )

    phase_number: int = Field(
        default=2,
        sa_column=Column(Integer, nullable=False, default=2)
    )

    # ----------------------
    # Link to School
    # ----------------------
    # For Academic Depts (Phase 1), this links to a School (e.g. CSE -> SOICT).
    # For Admin Depts (Phase 2/3), this can be None.
    school_id: Optional[int] = Field(default=None, foreign_key="schools.id")

    # ----------------------
    # Relationships
    # ----------------------
    
    # Parent School Relationship
    school: Optional["School"] = Relationship(back_populates="departments")

    # Users linked to this department (e.g. HODs, Librarians)
    users: List["User"] = Relationship(back_populates="department")

    # Students belonging to this academic department (e.g. CSE Students)
    students: List["Student"] = Relationship(back_populates="department")
    
    # Stages assigned to this department
    stages: List["ApplicationStage"] = Relationship(back_populates="department")
    
    programmes: List["Programme"] = Relationship(back_populates="department")