import pytest
from app.models.user import User, UserRole
from app.models.department import Department
from app.core.security import create_access_token

@pytest.mark.asyncio
async def test_admin_create_user(client, db_session):
    # 1. Create REAL Admin User
    admin = User(name="Admin", email="admin@create.com", role=UserRole.Admin, password_hash="pw")
    db_session.add(admin)
    await db_session.commit()

    # 2. Generate Token for THIS admin
    admin_token = create_access_token(subject=str(admin.id), data={"role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}

    dept = Department(name="Users Test Dept", code="UTD", phase_number=2)
    db_session.add(dept)
    await db_session.commit()

    payload = {
        "name": "Test Staff",
        "email": "staff_new@test.com",
        "password": "pw",
        "role": "staff",
        "department_code": dept.code
    }
    res = await client.post("/api/admin/register-user", json=payload, headers=headers)
    assert res.status_code == 201

@pytest.mark.asyncio
async def test_admin_list_users(client, db_session):
    # 1. Create REAL Admin User
    admin = User(name="Admin List", email="admin@list.com", role=UserRole.Admin, password_hash="pw")
    db_session.add(admin)
    await db_session.commit()

    # 2. Generate Token
    admin_token = create_access_token(subject=str(admin.id), data={"role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.get("/api/users/", headers=headers)
    assert res.status_code == 200