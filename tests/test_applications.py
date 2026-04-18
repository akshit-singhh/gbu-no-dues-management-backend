import pytest
import uuid
from app.models.user import UserRole
from app.core.security import create_access_token
from app.models.student import Student
from app.models.user import User
from app.models.school import School
from app.models.department import Department

VALID_PAYLOAD = {
    "proof_document_url": "uuid-123/file.pdf",
    "remarks": "My No Dues Request",
    "father_name": "Test Father",
    "mother_name": "Test Mother",
    "gender": "Male",
    "category": "General",
    "dob": "2000-01-01",
    "permanent_address": "123 Test St",
    "domicile": "UP",
    "is_hosteller": False,
    "batch": "2022-2026",
    "section": "A",
    "admission_year": 2022,
    "admission_type": "Regular",
    # "school_id" is not in ApplicationCreate schema, so it's not needed in payload
    # logic derives it from the student profile
}

@pytest.mark.asyncio
async def test_create_application_success(client, db_session):
    # 0. Seed School (Required Constraint)
    school = School(name="App School", dean_name="Dean")
    school.code = "SOAPP"
    db_session.add(school)
    await db_session.commit()

    dept = Department(name="App CSE", code="CSEAPP", phase_number=1, school_id=school.id)
    db_session.add(dept)
    await db_session.commit()

    # 1. Seed User
    user = User(name="Test Student", email="test@student.com", role=UserRole.Student, password_hash="pw")
    db_session.add(user)
    await db_session.commit()
    
    # 2. Seed Student 
    student = Student(
        full_name="Test Student", 
        email="test@student.com", 
        enrollment_number="EN123", 
        roll_number="RN123", 
        mobile_number="9999999999",
        user_id=user.id,
        school_id=school.id 
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    # 3. ✅ CRITICAL FIX: Link User to Student
    # The API checks `current_user.student_id`, so we must update the User record.
    user.student_id = student.id
    db_session.add(user)
    await db_session.commit()
    
    # 4. Token
    token = create_access_token(subject=str(user.id), data={"role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    # 5. API Call
    payload = dict(VALID_PAYLOAD)
    payload["department_code"] = dept.code
    response = await client.post("/api/applications/create", json=payload, headers=headers)
    assert response.status_code == 201

@pytest.mark.asyncio
async def test_get_my_application_signed_url(client, db_session):
    # 0. Seed School
    school = School(name="Signed School", dean_name="Dean")
    school.code = "SOSIG"
    db_session.add(school)
    await db_session.commit()

    # 1. Create User
    user = User(name="SignedURL User", email="signed@test.com", role=UserRole.Student, password_hash="pw")
    db_session.add(user)
    await db_session.commit()

    # 2. Create Student
    student = Student(
        full_name="Signed User",
        email="signed@test.com",
        enrollment_number="S100",
        roll_number="R100",
        mobile_number="123",
        user_id=user.id,
        school_id=school.id
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    # 3. ✅ CRITICAL FIX: Link User to Student
    user.student_id = student.id
    db_session.add(user)
    await db_session.commit()

    # 4. Token
    token = create_access_token(subject=str(user.id), data={"role": "student"})
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await client.get("/api/applications/my", headers=headers)
    # The endpoint returns 200 with { "application": None } if no app exists
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_create_duplicate_fails(client, db_session):
    # 0. Seed School
    school = School(name="Dup School", dean_name="Dean")
    school.code = "SODUP"
    db_session.add(school)
    await db_session.commit()

    dept = Department(name="Dup CSE", code="CSEDUP", phase_number=1, school_id=school.id)
    db_session.add(dept)
    await db_session.commit()

    # 1. Setup User 
    user = User(name="Dup Tester", email="dup@s.com", role=UserRole.Student, password_hash="pw")
    db_session.add(user)
    await db_session.commit()

    # 2. Setup Student
    stu = Student(
        full_name="Dup", 
        email="dup@s.com", 
        enrollment_number="D1", 
        roll_number="R1", 
        mobile_number="123",
        user_id=user.id,
        school_id=school.id
    )
    db_session.add(stu)
    await db_session.commit()
    await db_session.refresh(stu)

    # 3. ✅ CRITICAL FIX: Link User to Student
    user.student_id = stu.id
    db_session.add(user)
    await db_session.commit()

    # 4. Token
    token = create_access_token(subject=str(user.id), data={"role": "student"})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create App 1
    payload = dict(VALID_PAYLOAD)
    payload["department_code"] = dept.code
    await client.post("/api/applications/create", json=payload, headers=headers)
    
    # Create App 2 (Fail)
    res = await client.post("/api/applications/create", json=payload, headers=headers)
    assert res.status_code == 400