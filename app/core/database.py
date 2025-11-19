import ssl
from typing import AsyncGenerator

from sqlmodel import SQLModel
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings


def _make_ssl_context():
    """Create SSL context for database connection."""
    ctx = ssl.create_default_context()
    if not settings.DB_SSL_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


# Connect args for async engine
_connect_args = {"ssl": _make_ssl_context()}

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Dependency for FastAPI endpoints
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# Initialize database (create tables)
async def init_db() -> None:
    """Create tables declared via SQLModel (dev helper). Use Alembic for migrations in production."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# Test connection on startup
async def test_connection() -> None:
    """Simple connectivity test for startup logs; raises on failure."""
    try:
        async with engine.connect() as conn:
            # Wrap raw SQL in text()
            await conn.execute(text("SELECT 1"))
            print("✅ Successfully connected to database.")
    except Exception as e:
        print("❌ Database connection failed:")
        print("   →", e)
        raise


# Example helper for async queries (replace session.exec with session.execute)
async def get_user_by_email(session: AsyncSession, email: str):
    """
    Example helper function to fetch a user by email using AsyncSession.
    """
    from app.models.user import User  # Import your User model

    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()  # Returns User instance or None
