# app/api/endpoints/logs.py

from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional

# Database dependencies
from app.api.deps import get_db_session, require_admin

# Models
from app.models.user import User
from app.models.audit import AuditLog
from app.models.system_audit import SystemAuditLog

# Schemas
from app.schemas.audit import AuditLogRead, SystemAuditLogRead

# Define the router with the SAME prefix so frontend URLs don't break
router = APIRouter(prefix="/api/admin", tags=["Audit & Logs"])

# -------------------------------------------------------------------
# VIEW SYSTEM SECURITY LOGS (Admin actions, logins, rate limits)
# -------------------------------------------------------------------
@router.get("/system-logs", response_model=List[SystemAuditLogRead])
async def get_system_logs(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin), 
):
    """
    Fetches the system and security audit trail.
    Strictly for super-admins to monitor system health and security events.
    """
    query = select(SystemAuditLog).order_by(SystemAuditLog.timestamp.desc()).limit(limit)
    
    if event_type:
        query = query.where(SystemAuditLog.event_type == event_type)
    if status:
        query = query.where(SystemAuditLog.status == status)
        
    result = await session.execute(query)
    return result.scalars().all()


# -------------------------------------------------------------------
# VIEW BUSINESS WORKFLOW AUDIT LOGS
# -------------------------------------------------------------------
@router.get("/audit-logs", response_model=List[AuditLogRead])
async def get_audit_logs(
    action: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin), 
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    
    if action:
        query = query.where(AuditLog.action == action)
    if actor_role:
        query = query.where(AuditLog.actor_role == actor_role)
        
    result = await session.execute(query)
    return result.scalars().all()