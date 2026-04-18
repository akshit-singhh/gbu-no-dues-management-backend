import os
import ssl
from typing import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

# -------------------------------------------------------------------------
# 1. ENVIRONMENT CONFIGURATION
# -------------------------------------------------------------------------
_PRE_DOTENV_ENV = os.getenv("ENV", "development").lower()
load_dotenv(override=_PRE_DOTENV_ENV in {"development", "dev", "local", "test", "testing"})
ENV = os.getenv("ENV", "development").lower()


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _first_non_empty(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip(), name
    return None, None


def resolve_database_url(env_name: str) -> tuple[str, str]:
    env_name = (env_name or "development").lower()

    if env_name in {"development", "dev", "local"}:
        url, source = _first_non_empty(
            "DATABASE_URL_DEVELOPMENT",
            "DATABASE_URL_LOCAL",
            "LOCAL_DATABASE_URL",
            "DATABASE_URL",
        )
    elif env_name in {"production", "prod"}:
        url, source = _first_non_empty("DATABASE_URL_PRODUCTION", "DATABASE_URL")
    elif env_name in {"test", "testing"}:
        url, source = _first_non_empty(
            "DATABASE_URL_TEST",
            "TEST_DATABASE_URL",
            "DATABASE_URL_DEVELOPMENT",
            "DATABASE_URL",
        )
    else:
        url, source = _first_non_empty("DATABASE_URL")

    if not url or not source:
        raise RuntimeError(
            "❌ No database URL configured. Set DATABASE_URL or env-specific variables "
            "(DATABASE_URL_DEVELOPMENT / DATABASE_URL_PRODUCTION / DATABASE_URL_TEST)."
        )
    return url, source


DATABASE_URL, DATABASE_URL_SOURCE = resolve_database_url(ENV)


def normalize_database_url(url: str) -> tuple[str, bool, str]:
    """Normalize DB URL to async drivers and infer SSL requirement from query flags."""
    ssl_required = False

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    db_kind = "other"

    kept_params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lk = key.lower()
        if lk in {"ssl-mode", "sslmode"}:
            if str(value).upper() in {"REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY", "TRUE", "1"}:
                ssl_required = True
            # aiomysql doesn't support ssl-mode query arg directly.
            if scheme.startswith("mysql"):
                continue
        if lk == "ssl" and _is_truthy(value):
            ssl_required = True
        kept_params.append((key, value))

    cleaned_query = urlencode(kept_params)
    cleaned_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, cleaned_query, parsed.fragment))

    if cleaned_url.startswith("mysql+aiomysql://"):
        db_kind = "mysql"
        return cleaned_url, ssl_required, db_kind
    if cleaned_url.startswith("mysql://"):
        db_kind = "mysql"
        return cleaned_url.replace("mysql://", "mysql+aiomysql://", 1), ssl_required, db_kind
    if cleaned_url.startswith("mysql+pymysql://"):
        db_kind = "mysql"
        return cleaned_url.replace("mysql+pymysql://", "mysql+aiomysql://", 1), ssl_required, db_kind
    if cleaned_url.startswith("mysql+mysqldb://"):
        db_kind = "mysql"
        return cleaned_url.replace("mysql+mysqldb://", "mysql+aiomysql://", 1), ssl_required, db_kind
    if cleaned_url.startswith("postgresql+asyncpg://"):
        db_kind = "postgresql"
        return cleaned_url, ssl_required, db_kind
    if cleaned_url.startswith("postgresql://"):
        db_kind = "postgresql"
        return cleaned_url.replace("postgresql://", "postgresql+asyncpg://", 1), ssl_required, db_kind
    if cleaned_url.startswith("postgres://"):
        db_kind = "postgresql"
        return cleaned_url.replace("postgres://", "postgresql+asyncpg://", 1), ssl_required, db_kind
    if cleaned_url.startswith("postgresql+psycopg2://"):
        db_kind = "postgresql"
        return cleaned_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1), ssl_required, db_kind
    return cleaned_url, ssl_required, db_kind


DATABASE_URL, SSL_REQUIRED_FROM_URL, DB_KIND = normalize_database_url(DATABASE_URL)
DB_HOST = urlsplit(DATABASE_URL).hostname
IS_LOCAL_DB_HOST = DB_HOST in {"localhost", "127.0.0.1"}

logger.info(
    f"🗄️ Database URL resolved from {DATABASE_URL_SOURCE} | env={ENV} | driver={DB_KIND} | host={DB_HOST or 'unknown'}"
)


# -------------------------------------------------------------------------
# 2. SSL CONTEXT
# -------------------------------------------------------------------------
def make_ssl_context():
    """
    Creates SSL context for supported remote databases.
    """
    ca_path = os.getenv("DB_SSL_CA") or os.getenv("DB_CA_CERT_PATH")
    verify_ssl = _is_truthy(os.getenv("DB_SSL_VERIFY", "true"))

    if ca_path:
        if not os.path.exists(ca_path):
            raise RuntimeError("❌ SSL CA file not found. Check DB_SSL_CA path.")
        ctx = ssl.create_default_context(cafile=ca_path)
    else:
        ctx = ssl.create_default_context()

    if verify_ssl:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    return ctx


# -------------------------------------------------------------------------
# 3. CONNECTION ARGUMENTS
# -------------------------------------------------------------------------
force_ssl = _is_truthy(os.getenv("DB_USE_SSL", "false"))
ssl_enabled = SSL_REQUIRED_FROM_URL or force_ssl or (ENV == "production" and not IS_LOCAL_DB_HOST)

connect_args = {}
if ssl_enabled and DB_KIND in {"mysql", "postgresql"}:
    reason = []
    if SSL_REQUIRED_FROM_URL:
        reason.append("URL ssl flag")
    if force_ssl:
        reason.append("DB_USE_SSL")
    if ENV == "production" and not IS_LOCAL_DB_HOST:
        reason.append("production remote DB")
    logger.info(f"🔐 SSL Enabled ({', '.join(reason)})")
    connect_args["ssl"] = make_ssl_context()
else:
    logger.info("🛠 SSL Disabled for DB connection")


# -------------------------------------------------------------------------
# 4. ENGINE CONFIGURATION
# -------------------------------------------------------------------------
engine_kwargs = {
    "echo": False,  # Disable SQL logging in production for performance
    "future": True,
    "connect_args": connect_args,
    "pool_pre_ping": True,
}

# Non-SQLite engines benefit from pooled tuning.
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
            "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
            "pool_use_lifo": True,
        }
    )

engine = create_async_engine(DATABASE_URL, **engine_kwargs)


# -------------------------------------------------------------------------
# 5. SESSION FACTORY
# -------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


# -------------------------------------------------------------------------
# 6. DEPENDENCY INJECTION
# -------------------------------------------------------------------------
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency to yield a database session.
    Automatically handles commit/rollback logic via context manager.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"⚠️ Database Transaction Rollback: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


# -------------------------------------------------------------------------
# 7. LIFECYCLE HELPERS (Startup/Shutdown)
# -------------------------------------------------------------------------
async def init_db():
    """Initializes database tables. Should be run once on startup."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("✅ Database Schema Synced")
    except Exception as e:
        logger.critical(f"❌ DB Init Failed: {e}")
        raise


async def close_db():
    """Dispose pooled connections gracefully on app shutdown."""
    try:
        await engine.dispose()
        logger.info("🛑 Database engine disposed.")
    except Exception as e:
        logger.warning(f"⚠️ DB dispose failed: {e}")


async def test_connection():
    """Simple health check to verify latency and connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("🚀 Database Connected")
    except Exception as e:
        logger.critical(f"❌ Connection Failed: {e}")
        raise e