import pytest
import random
import string

def random_str(prefix="", length=6):
    chars = string.ascii_lowercase + string.digits
    return f"{prefix}{''.join(random.choices(chars, k=length))}"

@pytest.mark.asyncio
async def test_student_login_flow(client):
    unique_roll = random_str("ROLL")
    password = "securePassword123"

    # 1. Login Fail
    fail_payload = {
        "identifier": unique_roll,
        "password": password,
        "turnstile_token": "test-turnstile-token",
    }
    res_fail = await client.post("/api/students/login", json=fail_payload)
    assert res_fail.status_code == 401
    
    # ✅ FIX Assertion
    # Verify the error message contains 'Invalid credentials' OR 'Incorrect'
    error_msg = res_fail.json()["detail"]
    assert "Invalid credentials" in error_msg or "Incorrect" in error_msg