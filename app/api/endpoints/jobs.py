import hmac
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select
from loguru import logger
import os

from app.api.deps import get_db_session
from app.models.application_stage import ApplicationStage
from app.models.user import User
from app.models.department import Department
from app.services.email_service import send_pending_reminder_email

router = APIRouter(prefix="/api/jobs", tags=["Background Jobs"])

STALE_THRESHOLD_DAYS = 7


# ---------------------------------------------------------------------------
# Helper — safe async email wrapper
# ---------------------------------------------------------------------------

async def _safe_send_email(
    verifier_name: str,
    verifier_email: str,
    pending_count: int,
    department_names: list[str],
) -> None:
    """
    Sends a consolidated reminder email.
    Catches all exceptions so a single failure never crashes the background worker.
    """
    try:
        await send_pending_reminder_email(
            verifier_name=verifier_name,
            verifier_email=verifier_email,
            pending_count=pending_count,
            department_name=", ".join(department_names),
        )
        logger.info(f"Stale reminder sent → {verifier_email} ({pending_count} pending)")
    except Exception as e:
        logger.error(f"Email delivery failed for {verifier_email}: {e}")


# ---------------------------------------------------------------------------
# CRON endpoint
# ---------------------------------------------------------------------------

@router.post("/trigger-stale-notifications", status_code=status.HTTP_200_OK)
async def trigger_stale_notifications(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    x_job_secret: str = Header(..., alias="X-Job-Secret"),
):
    """
    CRON JOB ENDPOINT — call via scheduled job (Vercel cron, GitHub Actions, etc.).

    Authentication: pass the secret as the `X-Job-Secret` request header,
    never as a query parameter (query params are logged by proxies and APMs).

    Logic:
      1. Finds all (department, role) groups with pending stages older than 7 days.
      2. Fetches the relevant verifier users in two bulk queries (no N+1).
      3. Consolidates pending counts so each verifier receives exactly one email,
         even if they cover multiple departments.
      4. Queues emails as background tasks and returns immediately.
    """

    # ------------------------------------------------------------------
    # 1. Auth — constant-time comparison prevents timing attacks
    # ------------------------------------------------------------------
    expected = os.getenv("JOB_SECRET", "")
    if not expected or not hmac.compare_digest(x_job_secret, expected):
        logger.warning(
            f"Unauthorized cron attempt | ip={request.client.host} "
            f"path={request.url.path}"
        )
        # Slow down brute-force attempts without blocking the event loop
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

    # ------------------------------------------------------------------
    # 2. Find stale (dept, role) groups — single aggregation query
    # ------------------------------------------------------------------
    seven_days_ago = datetime.utcnow() - timedelta(days=STALE_THRESHOLD_DAYS)

    stale_res = await session.execute(
        select(
            ApplicationStage.department_id,
            ApplicationStage.verifier_role,
            func.count(ApplicationStage.id).label("pending_count"),
        )
        .where(ApplicationStage.status == "pending")
        .where(ApplicationStage.created_at <= seven_days_ago)
        .group_by(ApplicationStage.department_id, ApplicationStage.verifier_role)
    )
    stale_groups = stale_res.all()

    if not stale_groups:
        return {"status": "skipped", "message": "No stale applications found."}

    logger.info(f"Stale job: {len(stale_groups)} group(s) need attention.")

    # ------------------------------------------------------------------
    # 3. Bulk-fetch departments and users — no N+1 queries
    # ------------------------------------------------------------------
    dept_ids = list({g.department_id for g in stale_groups if g.department_id})
    roles = list({g.verifier_role for g in stale_groups})

    # One query for all departments
    dept_map: dict[int, str] = {}
    if dept_ids:
        dept_res = await session.execute(
            select(Department).where(Department.id.in_(dept_ids))
        )
        dept_map = {d.id: d.name for d in dept_res.scalars().all()}

    # One query for all relevant users
    user_res = await session.execute(
        select(User).where(User.role.in_(roles))
    )
    all_users = user_res.scalars().all()

    # Index users by (department_id, role) for O(1) lookup
    users_by_key: dict[tuple, list[User]] = defaultdict(list)
    for u in all_users:
        users_by_key[(u.department_id, u.role)].append(u)
        # Also index under (None, role) so role-only matches still work
        if u.department_id is not None:
            users_by_key[(None, u.role)].append(u)

    # ------------------------------------------------------------------
    # 4. Consolidate pending counts per verifier (one email per person)
    # ------------------------------------------------------------------
    # verifier_email → {"name": str, "total_pending": int, "depts": set}
    consolidated: dict[str, dict] = {}

    groups_skipped = 0

    for dept_id, role, count in stale_groups:
        dept_name = dept_map.get(dept_id, role.replace("_", " ").title())
        verifiers = users_by_key.get((dept_id, role), [])

        if not verifiers:
            logger.warning(f"No verifiers found | dept={dept_id} role={role}")
            groups_skipped += 1
            continue

        for verifier in verifiers:
            if not verifier.email:
                continue
            if verifier.email not in consolidated:
                consolidated[verifier.email] = {
                    "name": verifier.name,
                    "total_pending": 0,
                    "depts": set(),
                }
            consolidated[verifier.email]["total_pending"] += count
            consolidated[verifier.email]["depts"].add(dept_name)

    # ------------------------------------------------------------------
    # 5. Queue one consolidated email per verifier
    # ------------------------------------------------------------------
    emails_queued = 0
    for email, info in consolidated.items():
        background_tasks.add_task(
            _safe_send_email,
            verifier_name=info["name"],
            verifier_email=email,
            pending_count=info["total_pending"],
            department_names=sorted(info["depts"]),
        )
        emails_queued += 1

    logger.info(
        f"Stale job complete | groups={len(stale_groups)} "
        f"skipped={groups_skipped} emails_queued={emails_queued}"
    )

    return {
        "status": "success",
        "groups_found": len(stale_groups),
        "groups_skipped": groups_skipped,
        "groups_processed": len(stale_groups) - groups_skipped,
        "emails_queued": emails_queued,
    }