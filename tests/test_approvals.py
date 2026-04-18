import pytest
from app.models.user import User, UserRole
from app.core.security import create_access_token

@pytest.mark.asyncio
async def test_approvals_list_all_as_admin(client, db_session):
    # 1. Create Admin User in DB
    admin = User(name="Admin", email="admin@test.com", role=UserRole.Admin, password_hash="pw")
    db_session.add(admin)
    await db_session.commit()

    # 2. Generate Token for THIS admin
    admin_token = create_access_token(subject=str(admin.id), data={"role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.get("/api/approvals/all", headers=headers)
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_approvals_unauthorized(client):
    res = await client.get("/api/approvals/all")
    # FastAPI without auth header returns 403 Forbidden (Not Authenticated)
    assert res.status_code == 403