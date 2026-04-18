from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from sqlalchemy import Column, String

# FIX: Use TYPE_CHECKING to avoid runtime circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.department import Department

# ------------------------------------------------------------
# 1. PROGRAMME (e.g., B.Tech, M.Tech, BCA)
# ------------------------------------------------------------
class Programme(SQLModel, table=True):
    __tablename__ = "programmes"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(128), nullable=False))
    code: str = Field(sa_column=Column(String(20), nullable=False, unique=True, index=True))
    
    department_id: int = Field(foreign_key="departments.id")
    
    #FIX: Use String Forward Reference "Department"
    department: Optional["Department"] = Relationship(back_populates="programmes")
    
    specializations: List["Specialization"] = Relationship(back_populates="programme")

# ------------------------------------------------------------
# 2. SPECIALIZATION (e.g., AI, Data Science, VLSI)
# ------------------------------------------------------------
class Specialization(SQLModel, table=True):
    __tablename__ = "specializations"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(128), nullable=False))
    code: str = Field(sa_column=Column(String(20), nullable=False, unique=True, index=True))
    
    programme_id: int = Field(foreign_key="programmes.id")
    
    programme: Optional[Programme] = Relationship(back_populates="specializations")