import pytest
import random
import string
from app.models.school import School

def random_number(length=10):
    return ''.join(random.choices(string.digits, k=length))

def random_string(length=5):
    return ''.join(random.choices(string.ascii_letters, k=length))

@pytest.mark.asyncio
async def test_student_register_success(client, db_session):
    school = School(name=f"School {random_string()}", code=f"SO{random_number(4)}")
    db_session.add(school)
    await db_session.commit()

    enrollment = random_number(10)
    email = f"test.{random_string()}@example.com"
    
    payload = {
        "enrollment_number": enrollment,
        "roll_number": f"ROLL{random_number(5)}",
        "full_name": "Test Student Success",
        "mobile_number": random_number(10),
        "email": email,
        "password": "password123",
        "confirm_password": "password123",
        "school_code": school.code,
        "school_id": school.id,
        "turnstile_token": "test-turnstile-token",
    }

    res = await client.post("/api/students/register", json=payload)
    
    if res.status_code != 201:
        print(f"DEBUG Error: {res.json()}")

    assert res.status_code == 201
    data = res.json()
    assert data["student"]["email"] == email

@pytest.mark.asyncio
async def test_student_register_duplicate(client, db_session):
    school = School(name=f"School {random_string()}", code=f"SO{random_number(4)}")
    db_session.add(school)
    await db_session.commit()

    # Setup data
    enrollment = random_number(10)
    email = f"dup.{random_string()}@example.com"
    roll = f"ROLL{random_number(5)}"
    
    payload = {
        "enrollment_number": enrollment,
        "roll_number": roll,
        "full_name": "Original Student",
        "mobile_number": random_number(10),
        "email": email,
        "password": "password123",
        "confirm_password": "password123",
        "school_code": school.code,
        "school_id": school.id,
        "turnstile_token": "test-turnstile-token",
    }
    
    # 1. Register Success
    res1 = await client.post("/api/students/register", json=payload)
    assert res1.status_code == 201

    # 2. Register Duplicate -> Fail
    res2 = await client.post("/api/students/register", json=payload)
    assert res2.status_code == 400