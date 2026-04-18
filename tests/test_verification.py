import pytest
import uuid
from datetime import datetime
from app.models.student import Student
from app.models.application import Application
from app.models.certificate import Certificate
from app.models.school import School
from app.models.user import User, UserRole
from app.core.security import get_password_hash

@pytest.mark.asyncio
async def test_certificate_verification_success(client, db_session):
    # 0. Setup School
    school = School(name="Cert School", dean_name="Dean")
    school.code = "SOCERT"
    db_session.add(school)
    await db_session.commit()

    # 1. Setup Data
    student_id = uuid.uuid4()
    app_id = uuid.uuid4()
    cert_id = uuid.uuid4()
    cert_number = "GBU-TEST-2026"

    user = User(
        name="Verified Student",
        email="verify@test.com",
        role=UserRole.Student,
        password_hash=get_password_hash("pw"),
    )
    db_session.add(user)
    await db_session.commit()

    # Create Student
    student = Student(
        id=student_id,
        user_id=user.id,
        enrollment_number="VERIFY100",
        roll_number="VERIFY_ROLL",
        full_name="Verified Student",
        mobile_number="9999999999",
        email="verify@test.com",
        school_id=school.id # ✅ Linked
    )
    db_session.add(student)

    # Create Application
    application = Application(
        id=app_id,
        student_id=student_id,
        status="completed",
        proof_document_url="path/to/doc.pdf"
    )
    db_session.add(application)

    # Create Certificate
    certificate = Certificate(
        id=cert_id,
        application_id=app_id,
        certificate_number=cert_number,
        pdf_url="http://path.to/cert.pdf",
        generated_at=datetime.utcnow()
    )
    db_session.add(certificate)
    await db_session.commit()

    # 2. Test: Verify by UUID
    # NOTE: Ensure app/api/endpoints/verification.py has prefix="/api/verification"
    res_uuid = await client.get(f"/api/verification/verify/{cert_id}")
    assert res_uuid.status_code == 200

@pytest.mark.asyncio
async def test_password_reset_flow(client, db_session):
    # 1. Setup User
    email = "forgot@test.com"
    old_pw = "oldPass123"
    
    # Need to create School/Student if User links to them, 
    # but basic User doesn't strictly enforce student_id unless your model does.
    # Assuming basic user is fine:
    user = User(
        name="Forgot User",
        email=email,
        password_hash=get_password_hash(old_pw),
        role=UserRole.Student
    )
    db_session.add(user)
    await db_session.commit()

    # 2. Request OTP
    res_req = await client.post(
        "/api/verification/forgot-password",
        json={"email": email, "turnstile_token": "test-turnstile-token"},
    )
    assert res_req.status_code == 200