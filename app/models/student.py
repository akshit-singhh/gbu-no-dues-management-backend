from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Text, Integer, Boolean, String
from uuid import uuid4
from datetime import date, datetime
from typing import Optional
import uuid


class Student(SQLModel, table=True):
    __tablename__ = "students"

    id: uuid.UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    # Registration fields (FIXED: added real SQLAlchemy columns)
    enrollment_number: str = Field(
        sa_column=Column(String, nullable=False, unique=True)
    )

    roll_number: str = Field(
        sa_column=Column(String, nullable=False, unique=True)
    )

    full_name: str = Field(
        sa_column=Column(String, nullable=False)
    )

    mobile_number: str = Field(
        sa_column=Column(String, nullable=False)
    )

    email: str = Field(
        sa_column=Column(String, nullable=False, unique=True)
    )

    # Filled later during application
    father_name: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    mother_name: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )

    gender: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True)
    )

    category: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True)
    )

    dob: Optional[date] = Field(default=None)

    permanent_address: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    domicile: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    is_hosteller: Optional[bool] = Field(default=False)
    hostel_name: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    hostel_room: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )

    department_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True)
    )

    section: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    batch: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    admission_year: Optional[int] = Field(default=None)
    admission_type: Optional[str] = Field(
        default=None, sa_column=Column(String, nullable=True)
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
