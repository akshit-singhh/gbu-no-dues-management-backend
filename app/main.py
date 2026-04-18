from app.core.apm import bootstrap_datadog

bootstrap_datadog()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
import sys
import uuid
import os
import asyncio
import redis.asyncio as redis

# Database & Seeding
from app.core.database import test_connection, init_db, close_db
from app.core.seeding_logic import seed_all

# Rate Limiting
from slowapi.errors import RateLimitExceeded
from app.core.rate_limiter import limiter

# Config
from app.core.config import settings
from app.core.apm import bind_trace_context, tag_active_span, set_active_span_resource_for_request

# System Logging
from app.services.audit_service import log_system_event

# Routers
from app.api.endpoints import (
    auth as auth_router,
    users as users_router,
    account as account_router,
    applications as applications_router,
    students as students_router,
    auth_student as auth_student_router,
    approvals as approvals_router,
    verification as verification_router,
    utils as utils_router,
    jobs as jobs_router,
    common as common_router,
    logs as logs_router,
    metrics as metrics_router
)

# ------------------------------------------------------------
# LOGURU CONFIGURATION
# ------------------------------------------------------------
logger.remove()
logger.configure(patcher=bind_trace_context)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<magenta>trace_id={extra[dd_trace_id]} span_id={extra[dd_span_id]}</magenta> | "
           "<level>{level}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
           "<level>{message}</level>",
    colorize=True,
    backtrace=True,
    diagnose=True,
)

from app.core import storage

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting GBU No Dues Backend...")

    try:
        # 1. DATABASE CHECK
        await test_connection()
        logger.success("✅ Database connection established.")
        
        # 2. REDIS CHECK
        if settings.REDIS_URL:
            try:
                r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
                await r.ping()
                host = settings.REDIS_URL.split("@")[-1]
                logger.success(f"✅ Redis Connected: {host}")
                await r.close()
            except Exception as e:
                logger.error(f"❌ Redis Connection Failed: {e}")
        else:
            logger.warning("⚠️ No REDIS_URL found. Rate limiting is running in Memory (NOT Production Ready).")

        # 3. DB INIT & SEEDING
        await init_db()
        await seed_all()
        
        # -----------------------------
        # 4. FTP / Storage CHECK
        # -----------------------------
        if storage.STORAGE_BACKEND == "FTP":
            ftp_connected = storage.check_ftp_connection()
            if ftp_connected:
                logger.success(f"✅ FTP server reachable: {storage.FTP_HOST}:{storage.FTP_PORT}")
            else:
                logger.error(f"❌ FTP server not reachable: {storage.FTP_HOST}:{storage.FTP_PORT}")
        elif storage.STORAGE_BACKEND == "SUPABASE":
            logger.success("✅ Supabase storage backend selected.")

    except Exception as e:
        logger.error(f"⚠️ Startup sequence partial failure: {e}")

    yield
    logger.warning("🛑 Backend shutting down...")
    await close_db()

# ------------------------------------------------------------
# FASTAPI APP INIT
# ------------------------------------------------------------
app = FastAPI(
    title="GBU No Dues Backend",
    version="1.6.0",
    description="Backend service for the GBU No Dues Management System.",
    lifespan=lifespan,
)

app.state.limiter = limiter

# CUSTOM RATE LIMIT HANDLER TO TRACK DOS/BRUTE FORCE
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    client_ip = request.client.host if request.client else "Unknown"
    
    # Run the logging task in the background safely
    asyncio.create_task(
        log_system_event(
            event_type="SECURITY_BLOCK",
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
            new_values={
                "path": request.url.path, 
                "method": request.method, 
                "detail": "Rate limit exceeded (Too Many Requests)"
            },
            status="FAILURE"
        )
    )
    
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."}
    )

# ------------------------------------------------------------
# MIDDLEWARE
# ------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())

    tag_active_span(
        **{
            "http.request_id": request_id,
            "app.request.path": request.url.path,
            "app.request.url": str(request.url),
        }
    )
    logger.bind(request_id=request_id).info(f"{request.method} {request.url.path}")

    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path_format", None) or getattr(route, "path", None)
        set_active_span_resource_for_request(
            method=request.method,
            raw_path=request.url.path,
            route_path=route_path,
        )

        if response is not None:
            response.headers["X-Request-ID"] = request_id

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

@app.middleware("http")
async def traffic_stats_middleware(request: Request, call_next):
    # Skip tracking for internal routes or static files to save DB writes
    if not request.url.path.startswith(("/static", "/favicon.ico", "/docs", "/openapi.json")):
        try:
            if settings.REDIS_URL:
                # Fire and forget - don't await the connection setup too long
                r = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
                # Key Format: TRAFFIC:GET:/api/users
                key = f"TRAFFIC:{request.method}:{request.url.path}"
                await r.incr(key)
                await r.close()
        except Exception:
            # Never fail the request just because stats logging failed
            pass
            
    response = await call_next(request)
    return response

# ------------------------------------------------------------
# STATIC FILES (Vercel Friendly)
# ------------------------------------------------------------
# We wrap path creation in try/except because Vercel is Read-Only
try:
    if not os.path.exists("app/static/certificates"):
        os.makedirs("app/static/certificates", exist_ok=True)
except Exception:
    pass

if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ------------------------------------------------------------
# CORS (Fully Environment-Based)
# ------------------------------------------------------------
from fastapi.middleware.cors import CORSMiddleware

# Load origins from .env
env_origins = (
    [url.rstrip("/") for url in settings.FRONTEND_URL.split(",")]
    if settings.FRONTEND_URL
    else []
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=env_origins,  # Only from .env
    allow_origin_regex=settings.FRONTEND_REGEX or None,  # Optional regex support
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# ROUTERS
# ------------------------------------------------------------
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(account_router.router)
app.include_router(students_router.router)
app.include_router(auth_student_router.router)
app.include_router(applications_router.router)
app.include_router(approvals_router.router)
app.include_router(verification_router.router)
app.include_router(logs_router.router)
app.include_router(utils_router.router)
app.include_router(jobs_router.router)
app.include_router(common_router.router)
app.include_router(metrics_router.router)


@app.get("/", tags=["System"])
async def root():
    return {"status": "ok", "message": "Backend running successfully 🚀"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    fav_path = "app/static/favicon.ico"
    return FileResponse(fav_path) if os.path.exists(fav_path) else JSONResponse({"detail": "No favicon"}, status_code=404)