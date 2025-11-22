# app/models/user.py

from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as PGEnum  # <-- important
from datetime import datetime
import uuid
from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    Admin = "Admin"
    HOD = "HOD"
    Office = "Office"
    CellMember = "CellMember"
    Student = "Student"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    name: str = Field(nullable=False)
    email: str = Field(nullable=False, index=True, unique=True)
    password_hash: str = Field(nullable=False)

    # FIX: Bind SQLModel role field to real Postgres ENUM
    role: UserRole = Field(
        sa_column=Column(PGEnum(UserRole, name="user_role"), nullable=False)
    )

    department_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("departments.id"), nullable=True)
    )

    student_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
