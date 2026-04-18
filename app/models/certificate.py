from sqlmodel import SQLModel, Field, Column
from sqlalchemy import ForeignKey, DateTime, Text, String, Uuid
import uuid
from datetime import datetime
from typing import Optional

class Certificate(SQLModel, table=True):
    __tablename__ = "certificates"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(Uuid(as_uuid=True), primary_key=True)
    )

    # Corresponds to: application_id uuid null ... unique
    application_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), unique=True, nullable=True)
    )

    # Corresponds to: generated_by uuid null
    generated_by: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )

    # Corresponds to: pdf_url text not null
    pdf_url: str = Field(
        sa_column=Column(Text, nullable=False)
    )
    
    # Human Readable Certificate Number
    # e.g., GBU-ND-2025-AB12CD
    certificate_number: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50), nullable=True, unique=True)
    )

    # Corresponds to: generated_at timestamp with time zone ... default now()
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )