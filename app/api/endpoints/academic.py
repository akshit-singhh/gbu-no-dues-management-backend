from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session, require_admin
from app.models.academic import Programme, Specialization
from app.models.department import Department
from app.schemas.academic import (
    ProgrammeCreate, ProgrammeRead, 
    SpecializationCreate, SpecializationRead
)

router = APIRouter(prefix="/api/academic", tags=["Academic Structure"])

# =================================================================
# ADMIN: CREATE PROGRAMME
# =================================================================
@router.post("/programmes", response_model=ProgrammeRead)
async def create_programme(
    payload: ProgrammeCreate,
    session: AsyncSession = Depends(get_db_session),
    # _: User = Depends(require_admin) # Uncomment to protect
):
    # 1. Resolve Department
    dept = await session.execute(select(Department).where(Department.code == payload.department_code.upper()))
    dept = dept.scalar_one_or_none()
    if not dept:
        raise HTTPException(400, "Invalid Department Code")

    # 2. Create
    prog = Programme(name=payload.name, code=payload.code.upper(), department_id=dept.id)
    session.add(prog)
    await session.commit()
    await session.refresh(prog)
    return prog

# =================================================================
# ADMIN: CREATE SPECIALIZATION
# =================================================================
@router.post("/specializations", response_model=SpecializationRead)
async def create_specialization(
    payload: SpecializationCreate,
    session: AsyncSession = Depends(get_db_session),
):
    # 1. Resolve Programme
    prog = await session.execute(select(Programme).where(Programme.code == payload.programme_code.upper()))
    prog = prog.scalar_one_or_none()
    if not prog:
        raise HTTPException(400, "Invalid Programme Code")

    # 2. Create
    spec = Specialization(name=payload.name, code=payload.code.upper(), programme_id=prog.id)
    session.add(spec)
    await session.commit()
    await session.refresh(spec)
    return spec

# =================================================================
# PUBLIC: GET DROPDOWNS (Updated with Descriptive Mapping)
# =================================================================

@router.get("/programmes", response_model=List[ProgrammeRead])
async def get_programmes(
    department_code: Optional[str] = Query(None), # Made optional for "View All" support
    session: AsyncSession = Depends(get_db_session)
):
    """Fetch programmes with parent department details."""
    # 1. Join Department table to fetch name/code
    query = select(Programme).options(selectinload(Programme.department)).order_by(Programme.name)

    if department_code:
        query = query.join(Department).where(Department.code == department_code.upper().strip())
    
    result = await session.execute(query)
    items = result.scalars().all()

    # 2. Map descriptive fields for the UI
    for item in items:
        item.department_name = item.department.name if item.department else "N/A"
        item.department_code = item.department.code if item.department else "N/A"
    
    return items

@router.get("/specializations", response_model=List[SpecializationRead])
async def list_specializations(session: AsyncSession = Depends(get_db_session)):
    # 1. Fetch Specialization AND its Parent Programme
    stmt = (
        select(Specialization)
        .options(selectinload(Specialization.programme)) 
        .order_by(Specialization.name)
    )
    result = await session.execute(stmt)
    items = result.scalars().all()
    
    # 2. Map the parent data so the Schema can see it
    for item in items:
        if item.programme:
            item.programme_name = item.programme.name
            item.programme_code = item.programme.code
        else:
            item.programme_name = "Not Assigned"
            item.programme_code = "N/A"
            
    return items