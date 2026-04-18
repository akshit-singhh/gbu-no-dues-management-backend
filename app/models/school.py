from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Integer, String, Boolean

# Prevent circular imports
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.student import Student
    from app.models.application_stage import ApplicationStage
    from app.models.department import Department

class School(SQLModel, table=True):
    __tablename__ = "schools"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True)
    )

    name: str = Field(
        sa_column=Column(String(128), nullable=False, unique=True)
    )

    code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(20), unique=True, nullable=True)
    )

    # --------------------------------------------------------
    # DYNAMIC BUSINESS RULES
    # --------------------------------------------------------
    # Only LABS need to be toggled. Library is now mandatory for all.
    requires_lab_clearance: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, nullable=False),
        description="If False, students from this school skip the Lab stage."
    )

    # --------------------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------------------
    
    users: List["User"] = Relationship(back_populates="school")
    students: List["Student"] = Relationship(back_populates="school")
    stages: List["ApplicationStage"] = Relationship(back_populates="school")
    departments: List["Department"] = Relationship(back_populates="school")