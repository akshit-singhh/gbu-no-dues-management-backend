from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Integer, String, Text
from uuid import uuid4
from datetime import datetime
from typing import Optional
import uuid


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: uuid.UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    student_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    )

    # Set by office or super_admin
    office_verifier_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )

    status: str = Field(
        default="Pending",
        sa_column=Column(String, nullable=False)
    )

    current_department_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True)
    )

    remarks: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True)
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(String, nullable=False)
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(String, nullable=False)
    )
