from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional
from datetime import datetime


class StudentCreate(BaseModel):
    full_name: str
    roll_number: str
    email: EmailStr
    department_id: Optional[int] = None
    course: Optional[str] = None
    year_of_completion: Optional[int] = None


class StudentRead(BaseModel):
    id: UUID
    full_name: str
    roll_number: str
    email: EmailStr
    department_id: Optional[int]
    course: Optional[str]
    year_of_completion: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True
