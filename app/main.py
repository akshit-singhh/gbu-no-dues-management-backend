# app/main.py

from fastapi import FastAPI
from app.core.database import test_connection, init_db, AsyncSessionLocal
from app.core.config import settings
from app.services.auth_service import get_user_by_email, create_user
from app.models.user import UserRole

# Routers
from app.api.endpoints import auth as auth_router
from app.api.endpoints import users as users_router
from app.api.endpoints import account as account_router
from app.api.endpoints import applications as applications_router
from app.api.endpoints import students as students_router
from app.api.endpoints import auth_student as auth_student_router
from app.api.endpoints import approvals as approvals_router
from app.api.endpoints import department as department_router

# ------------------------------------------------------------
# APP INIT
# ------------------------------------------------------------
app = FastAPI(
    title="GBU No Dues Backend (SQLModel)",
    version="1.0.0",
    description="Backend service for the GBU No Dues Management System.",
)


# ------------------------------------------------------------
# REGISTER ROUTERS
# ------------------------------------------------------------
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(account_router.router)

app.include_router(students_router.router)
app.include_router(auth_student_router.router)

app.include_router(applications_router.router)
app.include_router(approvals_router.router)
app.include_router(department_router.router)

# ------------------------------------------------------------
# APPLICATION STARTUP EVENTS
# ------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    print("\n🚀 Starting NoDues Backend...")

    # 1) DB Connection Check
    try:
        await test_connection()
        print("✅ Successfully connected to database.")
    except Exception as e:
        print("❌ Startup aborted due to database connection error.")
        raise e

    # 2) Create tables if missing
    try:
        await init_db()
        print("✅ Database tables ready.")
    except Exception as e:
        print("⚠️ Table initialization failed:", e)
        raise e

    # 3) Seed Super Admin
    async with AsyncSessionLocal() as session:

        if not settings.SUPER_ADMIN_EMAIL or not settings.SUPER_ADMIN_PASSWORD:
            print("⚠️ Missing SUPER_ADMIN_EMAIL or SUPER_ADMIN_PASSWORD in .env. Skipping seed.")
            print("Application startup complete.\n")
            return

        existing = await get_user_by_email(session, settings.SUPER_ADMIN_EMAIL)

        if not existing:
            print(f"------ Seeding Super Admin ({settings.SUPER_ADMIN_EMAIL}) ------")
            await create_user(
                session=session,
                name=settings.SUPER_ADMIN_NAME or "Super Admin",
                email=settings.SUPER_ADMIN_EMAIL,
                password=settings.SUPER_ADMIN_PASSWORD,
                role=UserRole.Admin,  # correct Enum usage
            )
            print("🎉 Super Admin created successfully.")
        else:
            print("Super Admin already exists. Skipping seed.")

    print("-------- Application startup complete --------\n")


# ------------------------------------------------------------
# ROOT HEALTH CHECK ENDPOINT
# ------------------------------------------------------------
@app.get("/", tags=["System"])
async def root():
    return {
        "status": "ok",
        "service": "GBU No Dues Backend",
        "version": "1.0.0",
        "message": "Backend running successfully 🚀",
    }
