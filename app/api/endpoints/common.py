from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import func
from typing import Literal

from app.core.rate_limiter import limiter
from app.api.deps import get_db_session
from app.models.school import School
from app.models.department import Department
from app.models.academic import Programme, Specialization 

router = APIRouter(
    prefix="/api/common",
    tags=["Common / Metadata"]
)

# ----------------------------------------------------------
# SCHEMAS (Simple Data for Dropdowns)
# ----------------------------------------------------------
class SchoolOption(BaseModel):
    name: str
    code: str

class DeptOption(BaseModel):
    name: str
    code: str
    is_academic: bool

class ProgrammeOption(BaseModel):
    name: str
    code: str
    department_code: str

class SpecializationOption(BaseModel):
    name: str
    code: str
    programme_code: str

# ----------------------------------------------------------
# 1. GET ALL SCHOOLS
# ----------------------------------------------------------
@router.get("/schools", response_model=List[SchoolOption])
@limiter.limit("20/minute")
async def get_schools(
    request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    result = await session.execute(select(School).order_by(School.name))
    schools = result.scalars().all()
    return [SchoolOption(name=s.name, code=s.code) for s in schools]


class SchoolUpdate(BaseModel):
    requires_lab_clearance: bool

@router.patch("/{school_code}")
async def update_school(school_code: str, update_data: SchoolUpdate, session: AsyncSession = Depends(get_db_session)):
    # Look up the school by its string code (case-insensitive to be safe!)
    query = select(School).where(func.lower(School.code) == school_code.lower())
    result = await session.execute(query)
    school = result.scalar_one_or_none()
    
    if not school:
        raise HTTPException(status_code=404, detail=f"School with code '{school_code}' not found")
    
    school.requires_lab_clearance = update_data.requires_lab_clearance
    session.add(school)
    await session.commit()
    
    return {"message": f"{school.code} updated successfully"}

# ----------------------------------------------------------
# 2. GET DEPARTMENTS (Unified Dropdown API)
# ----------------------------------------------------------
@router.get("/departments", response_model=List[DeptOption])
async def get_departments(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    school_code: Optional[str] = Query(None, description="Filter by School Code (e.g., SOICT)"),
    type: Literal["academic", "all"] = Query("all", description="Filter by department type") 
):
    # 1. Base Query (Sort Alphabetically)
    query = select(Department).order_by(Department.name)
    
    # 2. FILTER: By Type (Crucial for "Create Program" dropdowns)
    if type == "academic":
        # Only show Academic Departments (Phase 1), hide Administration depts like Library
        query = query.where(Department.phase_number == 1)

    # 3. FILTER: By School Code (Crucial for "Student Registration")
    if school_code:
        # Case-insensitive match for robustness
        query = query.join(School).where(func.lower(School.code) == school_code.lower())
    
    # Execute
    result = await session.execute(query)
    depts = result.scalars().all()
    
    return [
        DeptOption(
            id=d.id,
            name=d.name,
            code=d.code, 
            is_academic=(d.phase_number == 1)
        ) 
        for d in depts
    ]
# ----------------------------------------------------------
# 3. GET PROGRAMMES (Support for Filtering)
# ----------------------------------------------------------
@router.get("/programmes", response_model=List[ProgrammeOption])
async def get_programmes(
    request: Request,
    department_code: Optional[str] = Query(None, description="Filter by Department Code"),
    session: AsyncSession = Depends(get_db_session)
):
    # Join Department to get the department code/name
    query = select(Programme, Department).join(Department).order_by(Programme.name)

    if department_code:
        query = query.where(Department.code == department_code.upper().strip())
    
    result = await session.execute(query)
    rows = result.all() 

    return [
        ProgrammeOption(
            id=p.id, # Useful if frontend needs ID later
            name=p.name, 
            code=p.code, 
            department_code=d.code 
        ) 
        for p, d in rows
    ]

# ----------------------------------------------------------
# 4. GET SPECIALIZATIONS (Full List or Filtered)
# ----------------------------------------------------------
@router.get("/specializations", response_model=List[SpecializationOption])
@limiter.limit("20/minute")
async def get_specializations(
    request: Request,
    # Made Optional: If not provided, returns ALL specializations
    programme_code: Optional[str] = Query(None, description="Filter by Programme Code (Optional)"),
    session: AsyncSession = Depends(get_db_session)
):
    query = select(Specialization, Programme).join(Programme).order_by(Specialization.name)

    if programme_code:
        query = query.where(Programme.code == programme_code.upper().strip())

    result = await session.execute(query)
    rows = result.all() # Returns tuples (Specialization, Programme)

    return [
        SpecializationOption(
            name=s.name, 
            code=s.code, 
            programme_code=p.code # Include Prog Code for frontend mapping
        ) 
        for s, p in rows
    ]