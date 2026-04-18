from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.application import ApplicationStatus # Ensure this enum is imported

# ============================================================
# 1. SHARED BASE
# ============================================================
class StudentBase(BaseModel):
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    dob: Optional[date] = None
    permanent_address: Optional[str] = None
    domicile: Optional[str] = None
    is_hosteller: Optional[bool] = None
    hostel_name: Optional[str] = None
    hostel_room: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# ============================================================
# 2. APPLICATION CREATE (POST)
# ============================================================
class ApplicationCreate(BaseModel):
    proof_document_url: str
    remarks: Optional[str] = None
    student_remarks: Optional[str] = None 

    # --- Profile Details ---
    father_name: str
    mother_name: str
    gender: str
    category: str
    dob: date
    permanent_address: str
    domicile: str
    
    # --- Academic Details (Hierarchy) ---
    department_code: str
    
    # ✅ NEW: Programme & Specialization
    programme_code: Optional[str] = None
    specialization_code: Optional[str] = None
    
    # --- Hostel Info ---
    is_hosteller: bool
    hostel_name: Optional[str] = None
    hostel_room: Optional[str] = None

    # --- Other Academic Details ---
    section: Optional[str] = None
    admission_year: int
    admission_type: str

# ============================================================
# 3. APPLICATION RESUBMIT (PATCH)
# ============================================================
class ApplicationResubmit(BaseModel):
    remarks: Optional[str] = None
    student_remarks: Optional[str] = None
    proof_document_url: Optional[str] = None

    # Allow fixing Department via Code
    department_code: Optional[str] = None

    # ✅ NEW: Allow fixing Programme & Specialization
    programme_code: Optional[str] = None
    specialization_code: Optional[str] = None

    # Profile fixes
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    dob: Optional[date] = None
    permanent_address: Optional[str] = None
    domicile: Optional[str] = None
    
    is_hosteller: Optional[bool] = None
    hostel_name: Optional[str] = None
    hostel_room: Optional[str] = None

    section: Optional[str] = None
    admission_year: Optional[int] = None
    admission_type: Optional[str] = None

# ============================================================
# 4. STUDENT UPDATE / READ
# ============================================================
class StudentUpdateData(StudentBase):
    pass 

class StudentUpdateWrapper(BaseModel):
    student_update: StudentUpdateData

class ApplicationRead(BaseModel):
    id: UUID
    display_id: Optional[str] = None
    student_id: UUID
    
    # Use Enum or str based on your preference
    status: ApplicationStatus 
    
    proof_document_url: Optional[str] = None
    current_stage_order: int = 1
    remarks: Optional[str] = None
    student_remarks: Optional[str] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Helper for frontend progress bar
    progress_percentage: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)