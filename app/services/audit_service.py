# app/services/audit_service.py

from uuid import UUID
from typing import Optional, Dict, Any
from app.models.audit import AuditLog
from app.models.system_audit import SystemAuditLog
from app.core.database import AsyncSessionLocal

# ==========================================
# 1. BUSINESS WORKFLOW LOGS (Departments)
# ==========================================
async def log_activity(
    action: str,
    actor_id: UUID,
    actor_role: Optional[str] = None,
    actor_name: Optional[str] = None,
    application_id: Optional[UUID] = None,
    remarks: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    Creates an audit log entry in a separate DB session.
    Safe for use in BackgroundTasks.
    """
    async with AsyncSessionLocal() as session:
        try:
            log_entry = AuditLog(
                actor_id=actor_id,
                actor_role=actor_role,
                actor_name=actor_name,
                application_id=application_id,
                action=action,
                remarks=remarks,
                details=details or {}
            )
            
            session.add(log_entry)
            await session.commit()
            
        except Exception as e:
            print(f"❌ AUDIT LOG ERROR: {str(e)}")
            await session.rollback()

# ==========================================
# 2. SYSTEM SECURITY LOGS (Admin actions)
# ==========================================
async def log_system_event(
    event_type: str,
    actor_id: Optional[UUID] = None,
    actor_role: Optional[str] = None, # ✅ ADDED PARAMETER
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    status: str = "SUCCESS"
):
    """
    Creates a system audit log entry for admin and security events.
    Safe for use in BackgroundTasks.
    """
    async with AsyncSessionLocal() as session:
        try:
            log_entry = SystemAuditLog(
                actor_id=actor_id,
                actor_role=actor_role, # ✅ SAVE IT HERE
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                old_values=old_values or {},
                new_values=new_values or {},
                status=status
            )
            
            session.add(log_entry)
            await session.commit()
            
        except Exception as e:
            print(f"❌ SYSTEM AUDIT LOG ERROR: {str(e)}")
            await session.rollback()