import pytest
import uuid
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.school import School
from app.core.security import create_access_token

def random_str(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:6]}"

@pytest.mark.asyncio
async def test_admin_list_students_flow(client, db_session):
    # 0. Setup School
    school = School(name="List School", dean_name="Dean")
    school.code = "SOLIST"
    db_session.add(school)
    
    # 1. Setup Admin User
    admin = User(name="Admin", email="admin@list.com", role=UserRole.Admin, password_hash="pw")
    db_session.add(admin)
    await db_session.commit()

    # 2. Seed linked Student User and Profile directly
    unique_roll = random_str("ROLL")
    student_user = User(
        name="List Test Student",
        email=f"{unique_roll}@test.com",
        role=UserRole.Student,
        password_hash="pw",
        school_id=school.id,
    )
    db_session.add(student_user)
    await db_session.commit()

    student = Student(
        enrollment_number=random_str("ENR"),
        roll_number=unique_roll,
        full_name="List Test Student",
        mobile_number="1234567890",
        email=student_user.email,
        school_id=school.id,
        user_id=student_user.id,
    )
    db_session.add(student)
    await db_session.commit()

    student_user.student_id = student.id
    db_session.add(student_user)
    await db_session.commit()

    # 3. Use Admin Token
    admin_token = create_access_token(subject=str(admin.id), data={"role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 4. Call Endpoint
    res = await client.get(f"/api/admin/students/{unique_roll}", headers=headers)
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_student_get_my_profile(client, db_session):
    # 0. Setup School
    school = School(name="Profile School", dean_name="Dean")
    school.code = "SOPROF"
    db_session.add(school)
    await db_session.commit()

    unique_roll = random_str("ME")
    email = f"{unique_roll}@me.com"

    # 1. Seed linked Student User and Profile directly
    student_user = User(
        name="Profile Tester",
        email=email,
        role=UserRole.Student,
        password_hash="pw",
        school_id=school.id,
    )
    db_session.add(student_user)
    await db_session.commit()

    student = Student(
        enrollment_number=random_str("ENR"),
        roll_number=unique_roll,
        full_name="Profile Tester",
        mobile_number="0000000000",
        email=email,
        school_id=school.id,
        user_id=student_user.id,
    )
    db_session.add(student)
    await db_session.commit()

    student_user.student_id = student.id
    db_session.add(student_user)
    await db_session.commit()

    token = create_access_token(subject=str(student_user.id), data={"role": "student"})
    
    # 3. Get Profile
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.get("/api/students/me", headers=headers)
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_students_unauthorized_routes(client):
    res_list = await client.get("/api/admin/students/UNKNOWN_ROLL")
    assert res_list.status_code == 403 # Expect 403