# app/services/email_service.py

import smtplib
import os
import asyncio
import concurrent.futures
from functools import partial
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader

from app.core.config import settings
from loguru import logger

# ---------------------------------------------------------------------------
# Jinja2 environment — built once at import time, not per call
# autoescape=True prevents XSS from user-supplied data in HTML emails
# ---------------------------------------------------------------------------
_TEMPLATE_DIR = os.path.join(
    os.path.abspath(os.getcwd()), "app", "templates", "email"
)
_JINJA_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=True,
)

# ---------------------------------------------------------------------------
# Bounded thread pool for blocking SMTP calls
# Caps concurrent SMTP threads — prevents thread exhaustion under load
# ---------------------------------------------------------------------------
_SMTP_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=5,
    thread_name_prefix="smtp",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_template(template_name: str):
    """Return a compiled Jinja2 template from the shared environment."""
    return _JINJA_ENV.get_template(template_name)


def _now_str(fmt: str = "%d-%m-%Y") -> str:
    """Current UTC time as a formatted string — consistent across timezones."""
    return datetime.now(timezone.utc).strftime(fmt)


# ---------------------------------------------------------------------------
# Core SMTP sender — blocking, runs in executor thread
# Raises on failure so callers can handle/retry as needed
# ---------------------------------------------------------------------------

def _send_via_smtp(to_email: str, subject: str, html_content: str) -> None:
    """
    Blocking SMTP send. Must be called via run_in_executor, never directly
    from an async context.
    """
    if not settings.SMTP_HOST:
        logger.warning(f"SMTP host not configured — email to {to_email} skipped.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Timeout=10 prevents threads from blocking indefinitely on a hung server
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            if settings.SMTP_PORT == 587:
                server.starttls()

        with server:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAILS_FROM_EMAIL, to_email, msg.as_string())

        logger.info(f"✅ Email sent to {to_email} | subject='{subject}'")
        
    except Exception as e:
        # Catch the connection error so it doesn't crash the background task!
        logger.error(f"❌ Failed to send email to {to_email}. SMTP Error: {e}")


# ---------------------------------------------------------------------------
# Async wrapper — offloads blocking SMTP to bounded executor
# ---------------------------------------------------------------------------

async def send_email_async(to_email: str, subject: str, html_content: str) -> None:
    """
    Non-blocking email send for use inside FastAPI route handlers and
    background tasks.

    Raises:
        Exception — propagates SMTP failures to the caller so they can
        decide whether to swallow, retry, or alert.
    """
    if not to_email:
        logger.error("send_email_async called with empty to_email — skipping.")
        return

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        _SMTP_EXECUTOR,
        partial(_send_via_smtp, to_email, subject, html_content),
    )


# ---------------------------------------------------------------------------
# 1. WELCOME EMAIL
# ---------------------------------------------------------------------------

async def send_welcome_email(student_data: dict) -> None:
    """
    Sent when a student account is created.

    Required keys: full_name, enrollment_number, roll_number, email
    """
    email = student_data.get("email")
    if not email:
        logger.error("send_welcome_email: missing 'email' in student_data.")
        return

    html_content = _get_template("student_welcome.html").render({
        "name": student_data.get("full_name", "Student"),
        "enrollment_number": student_data.get("enrollment_number", "N/A"),
        "roll_number": student_data.get("roll_number", "N/A"),
        "email": email,
        "login_url": f"{settings.FRONTEND_URL}/login",
    })

    await send_email_async(email, "Welcome to GBU No Dues Portal", html_content)


# ---------------------------------------------------------------------------
# 2. APPLICATION REJECTED EMAIL
# ---------------------------------------------------------------------------

async def send_application_rejected_email(data: dict) -> None:
    """
    Sent when a department rejects / returns an application.

    Required keys: email, name, department_name, remarks
    """
    email = data.get("email")
    if not email:
        logger.error("send_application_rejected_email: missing 'email'.")
        return

    html_content = _get_template("application_rejected.html").render({
        "name": data.get("name", "Student"),
        "department_name": data.get("department_name", ""),
        "remarks": data.get("remarks", ""),
        "rejection_date": _now_str(),
        "login_url": f"{settings.FRONTEND_URL}/login",
    })

    await send_email_async(
        email,
        "Action Required: No Dues Application Returned",
        html_content,
    )


# ---------------------------------------------------------------------------
# 3. APPLICATION APPROVED EMAIL
# ---------------------------------------------------------------------------

async def send_application_approved_email(data: dict) -> None:
    """
    Sent when all departments have cleared an application.

    Required keys: email, name, roll_number, enrollment_number,
                   display_id, application_id
    """
    email = data.get("email")
    if not email:
        logger.error("send_application_approved_email: missing 'email'.")
        return

    app_id = str(data.get("application_id", ""))

    html_content = _get_template("application_approved.html").render({
        "name": data.get("name", "Student"),
        "roll_number": data.get("roll_number", ""),
        "enrollment_number": data.get("enrollment_number", ""),
        "display_id": data.get("display_id", app_id),
        "application_id": app_id,
        "completion_date": _now_str(),
        "certificate_url": f"{settings.FRONTEND_URL}/certificate/download/{app_id}",
    })

    await send_email_async(
        email,
        "No Dues Application Approved",
        html_content,
    )


# ---------------------------------------------------------------------------
# 4. APPLICATION SUBMITTED EMAIL
# ---------------------------------------------------------------------------

async def send_application_created_email(data: dict) -> None:
    """
    Sent immediately after a student submits a no-dues application.

    Required keys: email, name, application_id
    Optional keys: display_id
    """
    email = data.get("email")
    if not email:
        logger.error("send_application_created_email: missing 'email'.")
        return

    app_id = str(data.get("application_id", ""))

    html_content = _get_template("application_created.html").render({
        "name": data.get("name", "Student"),
        "display_id": data.get("display_id") or app_id,
        "application_id": app_id,
        "submission_date": _now_str("%d-%m-%Y %I:%M %p"),
        "track_url": f"{settings.FRONTEND_URL}/dashboard",
    })

    await send_email_async(
        email,
        "Application Submitted Successfully - GBU No Dues",
        html_content,
    )


# ---------------------------------------------------------------------------
# 5. PASSWORD RESET OTP EMAIL
# ---------------------------------------------------------------------------

async def send_reset_password_email(data: dict) -> None:
    """
    Sends a 6-digit OTP for password reset.

    Required keys: email, otp
    Optional keys: name
    """
    email = data.get("email")
    if not email:
        logger.error("send_reset_password_email: missing 'email'.")
        return

    html_content = _get_template("password_reset.html").render({
        "name": data.get("name", "User"),
        "otp": data.get("otp", ""),
        "expiry_minutes": 15,
        "support_email": settings.EMAILS_FROM_EMAIL,
    })

    await send_email_async(
        email,
        "Password Reset OTP - GBU No Dues",
        html_content,
    )


# ---------------------------------------------------------------------------
# 6. PENDING REMINDER EMAIL (for verifiers / department heads)
# ---------------------------------------------------------------------------

async def send_pending_reminder_email(
    verifier_name: str,
    verifier_email: str,
    pending_count: int,
    department_name: str,
) -> None:
    """
    Reminds a verifier about applications pending for more than 7 days.
    Called by the stale-notifications cron job (jobs.py).
    """
    if not verifier_email:
        logger.error("send_pending_reminder_email: empty verifier_email — skipping.")
        return

    html_content = _get_template("pending_reminder.html").render({
        "verifier_name": verifier_name or "Verifier",
        "pending_count": pending_count,
        "department_name": department_name,
        "dashboard_url": f"{settings.FRONTEND_URL}/login",
    })

    await send_email_async(
        verifier_email,
        f"Action Required: {pending_count} Pending Applications",
        html_content,
    )