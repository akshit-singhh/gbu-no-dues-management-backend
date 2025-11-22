# app/services/application_service.py

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import uuid
from typing import Dict, Any, Optional

from app.models.application import Application
from app.models.student import Student


ALLOWED_STUDENT_UPDATE_FIELDS = {
    "full_name",
    "father_name",
    "mother_name",
    "gender",
    "category",
    "dob",
    "permanent_address",
    "domicile",
    "is_hosteller",
    "hostel_name",
    "hostel_room",
    "department_id",
    "section",
    "batch",
    "admission_year",
    "admission_type",
}


async def create_application_for_student(
    session: AsyncSession,
    student_id: str,
    payload: dict
):

    # 1. Fetch student
    result = await session.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise ValueError("Student not found")

    # 2. Check existing application
    existing_app_q = await session.execute(
        select(Application).where(Application.student_id == student.id)
    )
    existing_app = existing_app_q.scalar_one_or_none()

    if existing_app:
        if existing_app.status in ["Pending", "InProgress"]:
            # Student already has an active application – can't create new
            raise ValueError("You already have an active application.")

        if existing_app.status == "Completed":
            raise ValueError("Your application is already completed. No more submissions allowed.")

        if existing_app.status == "Rejected":
            # Resubmission process (do NOT create new application)
            await session.execute(
                "SELECT fn_resubmit_application(:app_id)",
                {"app_id": str(existing_app.id)}
            )
            await session.commit()

            return existing_app  # return the updated existing application

    # 3. Update student (allowed editable fields)
    student_update = payload.get("student_update") or {}
    for field, value in student_update.items():
        if hasattr(student, field):
            setattr(student, field, value)

    session.add(student)

    # 4. Create new application (only if none exists)
    app = Application(
        id=uuid.uuid4(),
        student_id=student.id,
        status="Pending",
        remarks=payload.get("remarks") if payload.get("remarks") else None
    )
    session.add(app)

    try:
        await session.commit()
        await session.refresh(app)
        return app
    except IntegrityError:
        await session.rollback()
        raise ValueError("Failed to create application")
