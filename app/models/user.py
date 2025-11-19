# app/models/user.py
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import String, DateTime
from typing import Optional
import uuid, enum
from datetime import datetime

class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    hod = "hod"
    staff = "staff"
    office = "office"
    student = "student"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[uuid.UUID] = Field(
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    email: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    password_hash: str = Field(sa_column=Column(String, nullable=False))
    role: str = Field(default=UserRole.staff.value, sa_column=Column(String, nullable=False))
    department_id: Optional[int] = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True))
    )
