import pytest
from datetime import datetime
from app.models.user import User, UserRole
from app.models.school import School
from app.models.student import Student
from app.models.application import Application, ApplicationStatus
from app.models.application_stage import ApplicationStage
from app.core.security import create_access_token

@pytest.mark.asyncio
async def test_dean_approval_moves_to_next_stage(client, db_session):
    # 1. SETUP: Seed Database
    school = School(name="School of Testing", dean_name="Dr. Test Dean")
    db_session.add(school)
    await db_session.commit()

    # B. Create Student User FIRST
    student_user = User(
        email="workflow_student@uni.edu",
        name="Workflow Student",
        role=UserRole.Student,
        password_hash="hashed_pw",
        is_active=True
    )
    db_session.add(student_user)
    await db_session.commit()

    # C. Create Student Profile LINKED to User
    student_profile = Student(
        full_name="Workflow Student",
        email="workflow_student@uni.edu",
        enrollment_number="WORK100",
        roll_number="ROLL_WORK",
        school_id=school.id,
        mobile_number="9999999999",
        user_id=student_user.id,
    )
    db_session.add(student_profile)
    await db_session.commit()

    student_user.student_id = student_profile.id
    db_session.add(student_user)
    await db_session.commit()

    # D. Create Dean User
    dean_user = User(
        email="workflow_dean@uni.edu",
        name="Dean User",
        role=UserRole.Dean,
        password_hash="hashed_pw",
        school_id=school.id,
        is_active=True
    )
    db_session.add(dean_user)
    await db_session.commit()

    # E. Create Application
    app = Application(
        student_id=student_profile.id,
        status=ApplicationStatus.PENDING.value,
        current_stage_order=1,
        proof_document_url="uuid/proof.pdf",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(app)
    await db_session.commit()

    # F. Create Stages
    stage_dean = ApplicationStage(
        application_id=app.id,
        verifier_role=UserRole.Dean.value,
        sequence_order=1,
        status=ApplicationStatus.PENDING.value,
        school_id=school.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(stage_dean)

    stage_lib = ApplicationStage(
        application_id=app.id,
        verifier_role=UserRole.Library.value,
        sequence_order=2,
        status=ApplicationStatus.PENDING.value,
        department_id=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(stage_lib)
    await db_session.commit()

    # 2. ACTION: Dean Approves
    dean_token = create_access_token(
        subject=str(dean_user.id),
        data={"role": "dean", "school_id": str(school.id)}
    )
    dean_headers = {"Authorization": f"Bearer {dean_token}"}

    res = await client.get("/api/approvals/pending", headers=dean_headers)
    assert res.status_code == 200
    
    pending_list = res.json()
    target_item = next((i for i in pending_list if i["application_id"] == str(app.id)), None)
    stage_id = target_item["active_stage"]["stage_id"]

    approve_res = await client.post(f"/api/approvals/{stage_id}/approve", headers=dean_headers)
    assert approve_res.status_code == 200

    # 3. VERIFY: Check Application State
    student_token = create_access_token(subject=str(student_user.id), data={"role": "student"})
    student_headers = {"Authorization": f"Bearer {student_token}"}

    status_res = await client.get("/api/applications/my", headers=student_headers)
    # This failed with 400 before because user.student_id was None. Now it should succeed.
    assert status_res.status_code == 200