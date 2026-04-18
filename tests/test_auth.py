import pytest
import random
import string
from app.models.user import User, UserRole
from app.core.security import get_password_hash

def random_str(prefix="", length=6):
    chars = string.ascii_lowercase + string.digits
    return f"{prefix}{''.join(random.choices(chars, k=length))}"

@pytest.mark.asyncio
async def test_admin_login_flow(client, db_session):
    unique_email = f"admin_{random_str()}@school.com"
    plain_password = "SecureAdminPassword123!"

    # 1. Login Fail
    fail_payload = {"email": unique_email, "password": plain_password, "turnstile_token": "test-turnstile-token"}
    res_fail = await client.post("/api/admin/login", json=fail_payload)
    assert res_fail.status_code == 401
    # ✅ FIX: Match actual API response
    assert "Invalid credentials" in res_fail.json()["detail"]

    # 2. Seed Admin
    # ✅ FIX: Use 'password_hash' to match DB column exactly
    admin_user = User(
        email=unique_email,
        name="Admin",
        password_hash=get_password_hash(plain_password), 
        role=UserRole.Admin,
        is_active=True
    )
    db_session.add(admin_user)
    await db_session.commit()

    # 3. Login Success
    success_payload = {"email": unique_email, "password": plain_password, "turnstile_token": "test-turnstile-token"}
    res_success = await client.post("/api/admin/login", json=success_payload)
    assert res_success.status_code == 200
    assert "access_token" in res_success.json()