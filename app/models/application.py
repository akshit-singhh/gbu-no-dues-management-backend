# app/models/application.py
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Integer, Text, DateTime, ForeignKey
from datetime import datetime
import uuid
from typing import Optional

class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    student_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("students.id"), nullable=False))
    office_verifier_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True))
    status: str = Field(default="Pending", sa_column=Column(Text, nullable=False))
    current_department_id: Optional[int] = Field(default=None, sa_column=Column(Integer, ForeignKey("departments.id"), nullable=True))
    remarks: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
