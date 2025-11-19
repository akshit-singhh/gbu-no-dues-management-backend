from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.exc import IntegrityError

from app.models.student import Student


async def create_student(session: AsyncSession, data) -> Student:
    student = Student(**data.dict())
    session.add(student)

    try:
        await session.commit()
        await session.refresh(student)
        return student
    except IntegrityError:
        await session.rollback()
        raise ValueError("Roll number already exists")


async def get_student_by_id(session: AsyncSession, student_id: str) -> Student | None:
    result = await session.execute(select(Student).where(Student.id == student_id))
    return result.scalar_one_or_none()


async def list_students(session: AsyncSession) -> list[Student]:
    result = await session.execute(select(Student))
    return result.scalars().all()
