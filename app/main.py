# app/main.py
from fastapi import FastAPI
from app.core.database import test_connection, init_db, AsyncSessionLocal
from app.core.config import settings
from app.services.auth_service import get_user_by_email, create_user
from app.models.user import UserRole
from app.api.endpoints import students as students_router


# Routers
from app.api.endpoints import auth as auth_router
from app.api.endpoints import users as users_router
from app.api.endpoints import account as account_router
from app.api.endpoints import applications as applications_router



app = FastAPI(
    title="GBU No Dues Backend (SQLModel)",
    version="1.0.0",
    description="Backend service for the GBU No Dues Management System.",
)

# ------------------------------------------------------------
# Register routers
# ------------------------------------------------------------
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(account_router.router)
app.include_router(applications_router.router)
app.include_router(students_router.router)

# ------------------------------------------------------------
# Application startup events
# ------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    print("\n🚀 Starting NoDues Backend...")

    # --- Verify DB connectivity ---
    try:
        await test_connection()
    except Exception as e:
        print("❌ Startup aborted due to database connection error.")
        raise e

    # --- Initialize database tables ---
    try:
        await init_db()
        print("✅ Database tables ready.")
    except Exception as e:
        print("⚠️ Table initialization failed:", e)
        raise e

    # --- Seed super admin ---
    async with AsyncSessionLocal() as session:
        existing_user = None
        if settings.SUPER_ADMIN_EMAIL:
            existing_user = await get_user_by_email(session, settings.SUPER_ADMIN_EMAIL)

        if not existing_user and settings.SUPER_ADMIN_EMAIL and settings.SUPER_ADMIN_PASSWORD:
            print(f"------Seeding Super Admin ------ ({settings.SUPER_ADMIN_EMAIL})...")
            await create_user(
                session,
                settings.SUPER_ADMIN_NAME or "Super Admin",
                settings.SUPER_ADMIN_EMAIL,
                settings.SUPER_ADMIN_PASSWORD,
                role=UserRole.super_admin,
            )
            print("Super Admin created successfully.")
        else:
            if existing_user:
                print("Super Admin already exists. Skipping seed.")
            else:
                print("⚠️ Missing SUPER_ADMIN_EMAIL or SUPER_ADMIN_PASSWORD in .env. Skipping seed.")

    print("Application startup complete.\n")


# ------------------------------------------------------------
# Root health-check endpoint
# ------------------------------------------------------------
@app.get("/", tags=["System"])
async def root():
    return {
        "status": "ok",
        "service": "GBU No Dues Backend",
        "version": "1.0.0",
        "message": "Backend running successfully 🚀",
    }
