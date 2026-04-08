import uuid

import pytest
from fastapi import HTTPException

from app.api.endpoints.academic import (
    create_programme,
    create_specialization,
    get_programmes,
    list_specializations,
)
from app.models.academic import Programme, Specialization
from app.models.department import Department
from app.schemas.academic import ProgrammeCreate, SpecializationCreate


pytestmark = pytest.mark.asyncio


def _u(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6].upper()}"


async def test_create_programme_success(db_session):
    dept = Department(name=f"Dept {_u('D')}", code=_u("CSE"))
    db_session.add(dept)
    await db_session.commit()

    payload = ProgrammeCreate(
        name="B.Tech CSE",
        code="btcs",
        department_code=dept.code.lower(),
    )

    created = await create_programme(payload=payload, session=db_session)
    assert created.name == "B.Tech CSE"
    assert created.code == "BTCS"
    assert created.department_id == dept.id


async def test_create_programme_invalid_department(db_session):
    payload = ProgrammeCreate(
        name="B.Tech Invalid",
        code="inv",
        department_code="does_not_exist",
    )

    with pytest.raises(HTTPException) as exc:
        await create_programme(payload=payload, session=db_session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid Department Code"


async def test_create_specialization_success(db_session):
    dept = Department(name=f"Dept {_u('D')}", code=_u("ECE"))
    db_session.add(dept)
    await db_session.commit()

    prog = Programme(name="B.Tech ECE", code=_u("BTE"), department_id=dept.id)
    db_session.add(prog)
    await db_session.commit()

    payload = SpecializationCreate(
        name="VLSI",
        code="vlsi",
        programme_code=prog.code.lower(),
    )

    created = await create_specialization(payload=payload, session=db_session)
    assert created.name == "VLSI"
    assert created.code == "VLSI"
    assert created.programme_id == prog.id


async def test_create_specialization_invalid_programme(db_session):
    payload = SpecializationCreate(
        name="Invalid",
        code="inv",
        programme_code="missing_prog",
    )

    with pytest.raises(HTTPException) as exc:
        await create_specialization(payload=payload, session=db_session)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid Programme Code"


async def test_get_programmes_empty_and_current_mapping_behavior(db_session):
    empty = await get_programmes(department_code=None, session=db_session)
    assert empty == []

    dept1 = Department(name=f"Dept {_u('D')}", code=_u("CSE"))
    dept2 = Department(name=f"Dept {_u('D')}", code=_u("MEC"))
    db_session.add(dept1)
    db_session.add(dept2)
    await db_session.commit()

    p1 = Programme(name="Programme A", code=_u("PA"), department_id=dept1.id)
    p2 = Programme(name="Programme B", code=_u("PB"), department_id=dept2.id)
    db_session.add(p1)
    db_session.add(p2)
    await db_session.commit()

    with pytest.raises(ValueError):
        await get_programmes(department_code=None, session=db_session)


async def test_list_specializations_empty(db_session):
    items = await list_specializations(session=db_session)
    assert items == []
