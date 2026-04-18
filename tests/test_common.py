import uuid

import pytest

from app.models.academic import Programme, Specialization
from app.models.department import Department
from app.models.school import School


pytestmark = pytest.mark.asyncio


def _u(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6].upper()}"


async def test_get_schools(client, db_session):
    school = School(name=f"School {_u('S')}", code=_u("SO"))
    db_session.add(school)
    await db_session.commit()

    res = await client.get("/api/common/schools")
    assert res.status_code == 200
    data = res.json()
    assert any(item["code"] == school.code for item in data)


async def test_update_school(client, db_session):
    school = School(name=f"School {_u('S')}", code=_u("SC"), requires_lab_clearance=True)
    db_session.add(school)
    await db_session.commit()

    res = await client.patch(
        f"/api/common/{school.code.lower()}",
        json={"requires_lab_clearance": False},
    )
    assert res.status_code == 200
    assert "updated successfully" in res.json()["message"]


async def test_get_departments_with_filters(client, db_session):
    school = School(name=f"School {_u('S')}", code=_u("SO"))
    db_session.add(school)
    await db_session.commit()

    academic_dept = Department(
        name=f"Academic {_u('D')}",
        code=_u("CSE"),
        phase_number=1,
        school_id=school.id,
    )
    admin_dept = Department(
        name=f"Admin {_u('D')}",
        code=_u("LIB"),
        phase_number=2,
    )
    db_session.add(academic_dept)
    db_session.add(admin_dept)
    await db_session.commit()

    res_all = await client.get("/api/common/departments")
    assert res_all.status_code == 200
    all_codes = {item["code"] for item in res_all.json()}
    assert academic_dept.code in all_codes
    assert admin_dept.code in all_codes

    res_academic = await client.get("/api/common/departments?type=academic")
    assert res_academic.status_code == 200
    academic_codes = {item["code"] for item in res_academic.json()}
    assert academic_dept.code in academic_codes
    assert admin_dept.code not in academic_codes

    res_school = await client.get(f"/api/common/departments?school_code={school.code.lower()}")
    assert res_school.status_code == 200
    school_codes = {item["code"] for item in res_school.json()}
    assert academic_dept.code in school_codes
    assert admin_dept.code not in school_codes


async def test_get_programmes_and_specializations_with_filters(client, db_session):
    school = School(name=f"School {_u('S')}", code=_u("SK"))
    db_session.add(school)
    await db_session.commit()

    dept = Department(
        name=f"Dept {_u('D')}",
        code=_u("IT"),
        phase_number=1,
        school_id=school.id,
    )
    other_dept = Department(name=f"Dept {_u('D')}", code=_u("EC"), phase_number=1)
    db_session.add(dept)
    db_session.add(other_dept)
    await db_session.commit()

    prog = Programme(name="B.Tech IT", code=_u("BIT"), department_id=dept.id)
    other_prog = Programme(name="B.Tech EC", code=_u("BEC"), department_id=other_dept.id)
    db_session.add(prog)
    db_session.add(other_prog)
    await db_session.commit()

    spec = Specialization(name="AI", code=_u("AI"), programme_id=prog.id)
    other_spec = Specialization(name="Comm", code=_u("CM"), programme_id=other_prog.id)
    db_session.add(spec)
    db_session.add(other_spec)
    await db_session.commit()

    res_programmes = await client.get(f"/api/common/programmes?department_code={dept.code.lower()}")
    assert res_programmes.status_code == 200
    prog_codes = {item["code"] for item in res_programmes.json()}
    assert prog.code in prog_codes
    assert other_prog.code not in prog_codes

    res_specs = await client.get(f"/api/common/specializations?programme_code={prog.code.lower()}")
    assert res_specs.status_code == 200
    spec_codes = {item["code"] for item in res_specs.json()}
    assert spec.code in spec_codes
    assert other_spec.code not in spec_codes
