# tests/conftest.py

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport 
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel

from app.main import app
from app.api.deps import get_db_session
from app.core.rate_limiter import limiter
# ✅ IMPORTANT: Import settings to force env vars to load
from app.core.config import settings 


# Allow PostgreSQL JSONB columns to be created on SQLite in tests.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture(autouse=True)
async def _bypass_turnstile(monkeypatch):
    async def _always_human(_token: str, ip: str = None):
        return True

    monkeypatch.setattr("app.api.endpoints.auth.verify_turnstile", _always_human)
    monkeypatch.setattr("app.api.endpoints.auth_student.verify_turnstile", _always_human)


@pytest_asyncio.fixture(autouse=True)
async def _disable_rate_limiter():
    limiter.enabled = False
    app.state.limiter.enabled = False

# 1. TEST DB SETUP
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    async with TestingSessionLocal() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

# 2. CLIENT SETUP
@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    
    # ✅ Fix: Use the standard transport setup
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()