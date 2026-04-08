import pytest

from app.core.security import create_access_token
from app.models.user import User, UserRole


pytestmark = pytest.mark.asyncio


async def _admin_headers(db_session):
    admin = User(
        name="Logs Admin",
        email="logs-admin@test.com",
        role=UserRole.Admin,
        password_hash="pw",
    )
    db_session.add(admin)
    await db_session.commit()
    token = create_access_token(subject=str(admin.id), data={"role": "admin"})
    return {"Authorization": f"Bearer {token}"}


async def test_get_system_logs_as_admin(client, db_session):
    headers = await _admin_headers(db_session)
    res = await client.get("/api/admin/system-logs", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_get_audit_logs_as_admin(client, db_session):
    headers = await _admin_headers(db_session)
    res = await client.get("/api/admin/audit-logs", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
