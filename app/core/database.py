# app/core/database.py

import ssl
from typing import AsyncGenerator

from sqlmodel import SQLModel
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings


# ------------------------------------------------------------
# SSL Setup
# ------------------------------------------------------------
def _make_ssl_context():
    ctx = ssl.create_default_context()
    if not settings.DB_SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


# ------------------------------------------------------------
# Engine Config
# ------------------------------------------------------------
_connect_args = {"ssl": _make_ssl_context()}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


# ------------------------------------------------------------
# IMPORTANT: Import ALL MODELS before create_all()
# ------------------------------------------------------------
# These imports LOAD MODELS into SQLModel.metadata
from app.models.department import Department
from app.models.user import User
from app.models.student import Student
from app.models.application import Application
# If you have these tables, import them too:
# from app.models.application_stage import ApplicationStage
# from app.models.audit_log import AuditLog
# from app.models.certificate import Certificate


# ------------------------------------------------------------
# Dependency for routes
# ------------------------------------------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ------------------------------------------------------------
# Create all tables (development only)
# ------------------------------------------------------------
async def init_db() -> None:
    """
    Create tables declared via SQLModel.
    Do NOT use this in production – use Alembic for migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# ------------------------------------------------------------
# Test DB Connection (Startup)
# ------------------------------------------------------------
async def test_connection() -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            print("✅ Successfully connected to database.")
    except Exception as e:
        print("❌ Database connection failed:")
        print(" →", e)
        raise e
