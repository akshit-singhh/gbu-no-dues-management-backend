# app/schemas/user.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from app.models.user import UserRole
import uuid

class UserRead(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    department_id: Optional[int] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    department_id: Optional[int] = None
