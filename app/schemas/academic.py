from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from typing import Optional
# --- PROGRAMME ---
class ProgrammeCreate(BaseModel):
    name: str
    code: str
    department_code: str 

class ProgrammeRead(BaseModel):
    id: int
    name: str
    code: str
    department_id: int
    department_name: Optional[str] = None
    department_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- SPECIALIZATION ---
class SpecializationCreate(BaseModel):
    name: str
    code: str
    programme_code: str 

class SpecializationRead(BaseModel):
    id: int
    name: str
    code: str
    programme_id: int
    programme_name: Optional[str] = None
    programme_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)