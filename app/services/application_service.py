from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import uuid
from datetime import datetime

from app.models.application import Application


async def create_application(
    session: AsyncSession,
    student_id: str,
    created_by_role: str,
    created_by_user_id: str,
    remarks: str | None,
) -> Application:
    """
    Create a new application.
    - If created by office or super_admin → set office_verifier_id
    - If created by student → leave it NULL, office will verify later
    """

    app = Application(
        id=uuid.uuid4(),
        student_id=student_id,
        office_verifier_id=(
            created_by_user_id if created_by_role in ["office", "super_admin"] else None
        ),
        status="Pending",
        current_department_id=None,   # Trigger will set the first dept
        remarks=remarks,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    session.add(app)
    await session.commit()
    await session.refresh(app)
    return app


async def get_application_by_id(session: AsyncSession, app_id: str) -> Application | None:
    result = await session.execute(select(Application).where(Application.id == app_id))
    return result.scalar_one_or_none()
