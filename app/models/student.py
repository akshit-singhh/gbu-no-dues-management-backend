from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import String, Integer
from uuid import uuid4
from datetime import datetime
from typing import Optional
import uuid


class Student(SQLModel, table=True):
    __tablename__ = "students"

    id: uuid.UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    full_name: str = Field(sa_column=Column(String, nullable=False))
    roll_number: str = Field(sa_column=Column(String, unique=True, nullable=False))
    email: str = Field(sa_column=Column(String, nullable=False))
    department_id: Optional[int] = Field(default=None, sa_column=Column(Integer))
    course: Optional[str] = None
    year_of_completion: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
