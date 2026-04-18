import pytest
import uuid
from app.models.user import User, UserRole
from app.models.department import Department
from app.core.security import create_access_token

def random_str(prefix="", length=6):
    import random, string
    chars = string.ascii_lowercase + string.digits
    return f"{prefix}{''.join(random.choices(chars, k=length))}"

@pytest.mark.asyncio
async def test_department_staff_can_view_pending(client, db_session):
    # 1. Department
    library_dept = Department(name="Library", code="LIBTEST", phase_number=2)
    db_session.add(library_dept)
    await db_session.commit()
    await db_session.refresh(library_dept)

    # 2. Staff User
    staff_user = User(
        email=f"lib_{random_str()}@uni.edu",
        name="Librarian",
        role=UserRole.Staff,
        department_id=library_dept.id,
        password_hash="hashed_pw", 
        is_active=True
    )
    db_session.add(staff_user)
    
    # 3. Student User (Optional background data)
    student_user = User(
        email=f"stu_{random_str()}@s.com", 
        name="Student", 
        role=UserRole.Student, 
        password_hash="pw"
    )
    db_session.add(student_user)
    
    # Commit to ensure IDs are generated
    await db_session.commit() 
    
    # 4. Generate Token for STAFF
    token = create_access_token(subject=str(staff_user.id), data={"role": "staff"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/approvals/pending", headers=headers)
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_student_cannot_access_department_actions(client, db_session):
    # 1. Create a Real Student User
    # We must create the user in the DB so `get_current_user` doesn't raise 401
    student = User(
        name="Auth Student",
        email=f"stu_{random_str()}@test.com",
        role=UserRole.Student,
        password_hash="pw",
        is_active=True
    )
    db_session.add(student)
    await db_session.commit()

    # 2. Generate Token for this REAL user
    student_token = create_access_token(subject=str(student.id), data={"role": "student"})
    headers = {"Authorization": f"Bearer {student_token}"}
    
    # 3. Attempt restricted action
    res = await client.post(f"/api/approvals/{uuid.uuid4()}/approve", headers=headers)
    
    # 4. Expect 403 Forbidden (Authenticated, but Role not allowed)
    assert res.status_code == 403