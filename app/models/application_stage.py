# app/models/application_stage.py
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid
from datetime import datetime
from typing import Optional

class ApplicationStage(SQLModel, table=True):
    __tablename__ = "application_stages"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True)
    )

    application_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    )

    department_id: int = Field(
        sa_column=Column(Integer, ForeignKey("departments.id"), nullable=False)
    )

    status: str = Field(
        sa_column=Column(String, nullable=False)
    )

    priority: str = Field(
        sa_column=Column(String, nullable=False, default="Low")
    )

    reviewer_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.id"))
    )

    remarks: Optional[str] = Field(
        default=None,
        sa_column=Column(String)
    )

    reviewed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )

    sequence_order: int = Field(
        sa_column=Column(Integer, nullable=False)
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True))
    )
