from pydantic import BaseModel
from uuid import UUID
from app.schemas.student import StudentRead

class StudentLoginRequest(BaseModel):
    identifier: str     # <-- enrollment_number OR roll_number
    password: str

class StudentLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    student_id: UUID
    student: StudentRead

    class Config:
        from_attributes = True
