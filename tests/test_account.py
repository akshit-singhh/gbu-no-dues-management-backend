import pytest
import uuid
from app.models.school import School
from app.models.user import User

def random_str(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:6]}"

@pytest.mark.asyncio
async def test_change_password_success(client, db_session):
    """
    Test the full flow: Register -> Login -> Change Password -> Login with New.
    """
    # 0. Setup School (Required for Registration)
    school = School(name="Account School", dean_name="Dr. Account")
    school.code = f"SO{uuid.uuid4().hex[:6].upper()}"
    db_session.add(school)
    await db_session.commit()

    # 1. Setup Unique User
    unique_roll = random_str("ROLL")
    unique_email = f"{unique_roll}@test.com"

    student_payload = {
        "enrollment_number": random_str("ENR"),
        "roll_number": unique_roll,
        "full_name": "Pwd Changer",
        "mobile_number": "1231231234",
        "email": unique_email,
        "password": "oldpassword123",
        "confirm_password": "oldpassword123",
        "school_code": school.code,
        "school_id": school.id,
        "turnstile_token": "test-turnstile-token"
    }

    # 2. Register
    reg_res = await client.post("/api/students/register", json=student_payload)
    assert reg_res.status_code == 201

    # 3. Login
    login_res = await client.post("/api/students/login", json={
        "identifier": unique_roll,
        "password": "oldpassword123",
        "turnstile_token": "test-turnstile-token"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Change Password
    change_payload = {
        "old_password": "oldpassword123",
        "new_password": "newpassword456"
    }
    change_res = await client.post("/api/account/change-password", json=change_payload, headers=headers)
    assert change_res.status_code == 200

    # 5. Login with New Password
    login_new = await client.post("/api/students/login", json={
        "identifier": unique_roll,
        "password": "newpassword456",
        "turnstile_token": "test-turnstile-token"
    })
    assert login_new.status_code == 200

@pytest.mark.asyncio
async def test_change_password_invalid_old(client, db_session):
    """
    Ensure the system blocks requests where 'old_password' is incorrect.
    """
    # 0. Setup School
    school = School(name="Account School 2", dean_name="Dr. Account")
    school.code = f"SO{uuid.uuid4().hex[:6].upper()}"
    db_session.add(school)
    await db_session.commit()

    # 1. Setup Unique User
    unique_roll = random_str("ROLL_FAIL")
    unique_email = f"{unique_roll}@test.com"

    student_payload = {
        "enrollment_number": random_str("ENR"),
        "roll_number": unique_roll,
        "full_name": "Bad Actor",
        "mobile_number": "9999999999",
        "email": unique_email,
        "password": "securepassword",
        "confirm_password": "securepassword",
        "school_code": school.code,
        "school_id": school.id,
        "turnstile_token": "test-turnstile-token"
    }

    # 2. Register & Login
    await client.post("/api/students/register", json=student_payload)
    login_res = await client.post("/api/students/login", json={
        "identifier": unique_roll,
        "password": "securepassword",
        "turnstile_token": "test-turnstile-token"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Try changing with WRONG old password
    change_payload = {
        "old_password": "WRONGpassword",
        "new_password": "newpassword456"
    }
    res = await client.post("/api/account/change-password", json=change_payload, headers=headers)
    assert res.status_code == 400