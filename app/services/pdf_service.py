# app/services/certificate_service.py

import os
import io
import uuid
import base64
import qrcode
import asyncio
import ssl
import atexit
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from ftplib import FTP, FTP_TLS, error_perm

from weasyprint import HTML
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from loguru import logger

from app.core.config import settings
from app.models.application import Application
from app.models.student import Student
from app.models.application_stage import ApplicationStage
from app.models.department import Department
from app.models.user import User
from app.models.certificate import Certificate

# =====================================================================
# CUSTOM FTP_TLS — fixes 425 TLS session resumption error
# =====================================================================

class ResumedFTP_TLS(FTP_TLS):
    """Extends FTP_TLS to reuse the control channel TLS session on the data channel."""

    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


# =====================================================================
# CONFIGURATION
# =====================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

MAX_PDF_SIZE = 5 * 1024 * 1024  # 5 MB — enforced before upload

# Bounded executor for CPU-bound PDF generation.
# Shut down cleanly on process exit so in-flight renders finish.
_pdf_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pdf")
atexit.register(_pdf_executor.shutdown, wait=True)

# Jinja2 environment — module-level singleton, autoescape on
from jinja2 import Environment, FileSystemLoader
_template_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

# Supabase client (optional)
try:
    from app.core.supabase_client import supabase  # type: ignore
except ImportError:
    supabase = None


# =====================================================================
# HELPERS
# =====================================================================

def _image_to_base64(path: str) -> str:
    if not os.path.exists(path):
        logger.warning(f"Image not found for base64 encoding: {path}")
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _generate_pdf_sync(html_content: str) -> bytes:
    """CPU-bound — must run in executor, never directly on the event loop."""
    return HTML(string=html_content).write_pdf(presentational_hints=True)


def _utcnow() -> datetime:
    """Timezone-aware UTC datetime — use everywhere instead of datetime.now() / utcnow()."""
    return datetime.now(timezone.utc)


def _ftp_mkdirs(ftp: FTP, path: str) -> None:
    """Recursively create FTP directories, ignoring already-exists errors."""
    parts = path.strip("/").split("/")
    accumulated = ""
    for part in parts:
        if not part:
            continue
        accumulated += f"/{part}"
        try:
            ftp.mkd(accumulated)
        except error_perm:
            pass  # directory already exists — expected


def _ftp_upload(pdf_bytes: bytes, ftp_dir: str, pdf_name: str) -> None:
    """
    Blocking FTP upload. Runs in executor.
    Reads FTP credentials fresh from env on every call so rotated
    secrets are picked up without a restart.
    Raises on any failure — never silently swallows errors.
    """
    ftp_host = os.environ.get("FTP_HOST")
    ftp_port = int(os.environ.get("FTP_PORT", 21))
    ftp_user = os.environ.get("FTP_USER")
    ftp_password = os.environ.get("FTP_PASSWORD")
    ftp_passive = os.environ.get("FTP_PASSIVE_MODE", "True").lower() in ("true", "1", "yes")
    ftp_use_tls = os.environ.get("FTP_USE_TLS", "True").lower() in ("true", "1", "yes")

    if not all([ftp_host, ftp_user, ftp_password]):
        raise RuntimeError("FTP credentials are not fully configured.")

    ftp: FTP = ResumedFTP_TLS() if ftp_use_tls else FTP()

    try:
        ftp.connect(host=ftp_host, port=ftp_port, timeout=30)

        if ftp_use_tls:
            ftp = ftp  # type already correct
            ftp.auth()
            ftp.login(user=ftp_user, passwd=ftp_password)
            ftp.prot_p()
        else:
            ftp.login(user=ftp_user, passwd=ftp_password)

        ftp.set_pasv(ftp_passive)

        # Ensure destination directory exists
        try:
            ftp.cwd(ftp_dir)
        except error_perm:
            _ftp_mkdirs(ftp, ftp_dir)
            ftp.cwd(ftp_dir)

        # Upload — SSLEOFError here means a partial/failed write; always re-raise
        ftp.storbinary(f"STOR {pdf_name}", io.BytesIO(pdf_bytes))

    finally:
        # Always attempt a clean disconnect, even on error
        try:
            ftp.quit()
        except Exception:
            pass


def _supabase_upload(pdf_bytes: bytes, pdf_name: str) -> str:
    """
    Blocking Supabase upload. Runs in executor.
    Returns the public URL of the uploaded file.
    Raises on failure.
    """
    if not supabase:
        raise RuntimeError("Supabase client is not initialised.")

    supabase.storage.from_("certificates").upload(
        file=pdf_bytes,
        path=pdf_name,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return supabase.storage.from_("certificates").get_public_url(pdf_name).split("?")[0]


# =====================================================================
# MAIN FUNCTION
# =====================================================================

async def generate_certificate_pdf(
    session: AsyncSession,
    application_id: uuid.UUID,
    generated_by_id: uuid.UUID | None = None,
) -> bytes:
    """
    Generates a no-dues certificate PDF for the given application:

    1. Fetches application, student, and stage data (with explicit 404s).
    2. Renders an HTML template with a QR code and university logo.
    3. Converts HTML → PDF in a bounded thread executor (non-blocking).
    4. Validates PDF size before attempting upload.
    5. Uploads to Supabase or FTP (both run in executor — non-blocking).
    6. Saves / updates the Certificate record in the database.
    7. Returns the raw PDF bytes for the HTTP response.
    """

    loop = asyncio.get_running_loop()

    # ------------------------------------------------------------------
    # 1. Fetch application
    # ------------------------------------------------------------------
    application = (await session.execute(
        select(Application).where(Application.id == application_id)
    )).scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")

    # ------------------------------------------------------------------
    # 2. Fetch student with related objects
    # ------------------------------------------------------------------
    student = (await session.execute(
        select(Student)
        .options(
            selectinload(Student.school),
            selectinload(Student.department),
            selectinload(Student.programme),
            selectinload(Student.specialization),
        )
        .where(Student.id == application.student_id)
    )).scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=404, detail="Student record not found.")

    # ------------------------------------------------------------------
    # 3. Fetch and format application stages
    # ------------------------------------------------------------------
    stages_raw = (await session.execute(
        select(ApplicationStage, Department.name, User.name, Department.code)
        .outerjoin(Department, ApplicationStage.department_id == Department.id)
        .outerjoin(User, ApplicationStage.verified_by == User.id)
        .where(ApplicationStage.application_id == application.id)
        .order_by(ApplicationStage.sequence_order)
    )).all()

    ACADEMIC_ROLES = {"HOD", "DEAN", "PROGRAM_COORDINATOR"}
    formatted_stages = []

    for i, (stage, dept_name, reviewer_name, dept_code) in enumerate(stages_raw):
        role_key = stage.verifier_role.upper() if stage.verifier_role else "UNKNOWN"

        if i == 0:
            display_name = "School Office"
        elif role_key == "HOD":
            display_name = f"HOD ({dept_code or dept_name})"
        elif role_key == "DEAN":
            display_name = f"Dean ({dept_name})" if dept_name else "School Dean"
        elif role_key in ACADEMIC_ROLES:
            display_name = dept_name or role_key.replace("_", " ").title()
        else:
            display_name = dept_name or role_key.replace("_", " ").title()

        formatted_stages.append({
            "department_name": display_name,
            "status": "Approved" if stage.status == "approved" else "Pending",
            "reviewer_name": reviewer_name or "System",
            "reviewed_at": (
                stage.verified_at.strftime("%d-%m-%Y") if stage.verified_at else "-"
            ),
        })

    # ------------------------------------------------------------------
    # 4. Resolve or generate certificate number
    # ------------------------------------------------------------------
    existing_cert = (await session.execute(
        select(Certificate).where(Certificate.application_id == application.id)
    )).scalar_one_or_none()

    if existing_cert:
        readable_id = existing_cert.certificate_number
    else:
        # Generate a new ID — uniqueness guaranteed by DB constraint on
        # certificate_number; if a race produces a duplicate the INSERT will
        # raise an IntegrityError rather than silently overwrite.
        readable_id = f"GBU-ND-{_utcnow().year}-{uuid.uuid4().hex[:5].upper()}"

    # ------------------------------------------------------------------
    # 5. Build QR code and encode assets
    # ------------------------------------------------------------------
    certificate_url = f"{settings.FRONTEND_URL}/verify/{readable_id}"
    qr = qrcode.QRCode(
        box_size=10,
        border=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
    )
    qr.add_data(certificate_url)
    qr.make(fit=True)
    qr_buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(qr_buffer, format="PNG")
    qr_base64 = base64.b64encode(qr_buffer.getvalue()).decode()

    logo_base64 = _image_to_base64(os.path.join(STATIC_DIR, "images", "gbu_logo.png"))

    now = _utcnow()
    context = {
        "student": student,
        "stages": formatted_stages,
        "certificate_id": readable_id,
        "generation_date": now.strftime("%d-%m-%Y"),
        "current_year": now.year,
        "qr_base64": qr_base64,
        "logo_base64": logo_base64,
    }

    html_content = _template_env.get_template("pdf/certificate_template.html").render(context)

    # ------------------------------------------------------------------
    # 6. Generate PDF in executor (CPU-bound, non-blocking)
    # ------------------------------------------------------------------
    pdf_bytes: bytes = await loop.run_in_executor(
        _pdf_executor, _generate_pdf_sync, html_content
    )

    # Guard against runaway templates producing oversized PDFs
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise ValueError(
            f"Generated PDF is too large ({len(pdf_bytes):,} bytes). "
            f"Limit is {MAX_PDF_SIZE:,} bytes."
        )

    # ------------------------------------------------------------------
    # 7. Upload to storage backend (both run in executor — non-blocking)
    # ------------------------------------------------------------------
    storage_backend = os.environ.get(
        "STORAGE", os.environ.get("STORAGE_BACKEND", "FTP")
    ).upper()

    pdf_name = f"certificate_{application.id}.pdf"
    pdf_url = ""

    try:
        if storage_backend == "SUPABASE":
            # Supabase SDK is synchronous — run in executor
            pdf_url = await loop.run_in_executor(
                _pdf_executor,
                lambda: _supabase_upload(pdf_bytes, pdf_name),
            )
            logger.info(f"Certificate uploaded to Supabase: {pdf_url}")

        elif storage_backend == "FTP":
            ftp_cert_dir = os.environ.get("FTP_CERTIFICATE_DIR", "/certificates")
            ftp_dir = f"{ftp_cert_dir}/{application.student_id}"

            # FTP is synchronous — run in executor
            await loop.run_in_executor(
                _pdf_executor,
                lambda: _ftp_upload(pdf_bytes, ftp_dir, pdf_name),
            )

            # Store a structured path; construct a real URL at serve time
            pdf_url = f"{ftp_dir}/{pdf_name}"
            logger.info(f"Certificate uploaded to FTP: {pdf_url}")

        else:
            logger.warning(f"Unknown STORAGE backend '{storage_backend}' — skipping upload.")

    except Exception as e:
        # Upload failure is logged but does NOT abort the request —
        # the PDF bytes are still returned and the DB record is saved
        # without a URL so a re-upload can be triggered later.
        logger.error(f"Storage upload failed for application {application_id}: {e}")
        pdf_url = ""

    # ------------------------------------------------------------------
    # 8. Persist certificate record
    # ------------------------------------------------------------------
    now_dt = _utcnow()

    if existing_cert:
        existing_cert.pdf_url = pdf_url
        existing_cert.generated_at = now_dt
        session.add(existing_cert)
    else:
        session.add(Certificate(
            id=uuid.uuid4(),
            application_id=application.id,
            certificate_number=readable_id,
            pdf_url=pdf_url,
            generated_at=now_dt,
            generated_by=generated_by_id,
        ))

    await session.commit()

    return pdf_bytes