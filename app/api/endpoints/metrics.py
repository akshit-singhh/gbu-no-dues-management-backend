from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select
import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
import asyncio
import time
import socket
import os
from loguru import logger

from app.core.config import settings
from app.api.deps import get_db_session, require_admin
from app.models.user import User
from app.models.application import Application
from app.models.application_stage import ApplicationStage
from app.models.department import Department
from app.models.audit import AuditLog
from app.core.database import test_connection

router = APIRouter(
    prefix="/api/metrics",
    tags=["System & Metrics"]
)

# Captured once when the module loads — used as uptime fallback when
# DEPLOY_TIMESTAMP env var is not set (e.g. local dev).
_SERVER_START_TIME = int(time.time())

# Cooldown window to avoid hammering Redis and flooding logs when upstream is unstable.
_REDIS_METRICS_COOLDOWN_SECONDS = 30
_redis_metrics_cooldown_until = 0.0
_redis_metrics_last_reason = "unknown"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redis_client(timeout: int = 2) -> redis.Redis:
    """Return a configured async Redis client (caller must close it)."""
    return redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
        retry_on_timeout=True,
    )


def _redis_metrics_in_cooldown() -> bool:
    return time.time() < _redis_metrics_cooldown_until


def _mark_redis_metrics_cooldown(reason: str) -> None:
    global _redis_metrics_cooldown_until, _redis_metrics_last_reason
    _redis_metrics_cooldown_until = time.time() + _REDIS_METRICS_COOLDOWN_SECONDS
    _redis_metrics_last_reason = reason
    logger.warning(
        f"Redis metrics degraded: {reason}. Cooling down for {_REDIS_METRICS_COOLDOWN_SECONDS}s."
    )


def _redis_metrics_cooldown_response(status: str) -> dict:
    retry_after = max(1, int(_redis_metrics_cooldown_until - time.time()))
    return {
        "status": status,
        "message": f"Redis temporarily unavailable ({_redis_metrics_last_reason}).",
        "retry_after_seconds": retry_after,
    }


async def _safe_close_redis(client) -> None:
    """Best-effort redis close: never fail request on teardown."""
    if not client:
        return
    try:
        await client.aclose()
    except Exception as e:
        logger.warning(f"Redis close warning: {e}")


async def _write_audit(session: AsyncSession, user: User, action: str, detail: str) -> None:
    """Persist an audit record for admin actions."""
    log = AuditLog(
        user_id=user.id,
        action=action,
        detail=detail,
    )
    session.add(log)
    await session.commit()


# ---------------------------------------------------------------------------
# 1. PUBLIC HEARTBEAT  –  minimal, no infra details
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check():
    """
    Public liveness probe.
    Returns only {"status": "ok"} — no infrastructure details exposed.
    Use /health/details (admin-only) for the full diagnostic view.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. ADMIN DIAGNOSTIC HEALTH  –  full infra details, gated
# ---------------------------------------------------------------------------

@router.get("/health/details")
async def health_details(_: User = Depends(require_admin)):
    """
    Admin-only endpoint.
    Returns database, Redis, and SMTP connectivity with latencies.
    """
    # Uptime — prefer DEPLOY_TIMESTAMP env var (set at deploy time, survives
    # serverless cold starts). Falls back to module load time in local dev.
    deploy_ts = int(os.environ.get("DEPLOY_TIMESTAMP", _SERVER_START_TIME))
    uptime_seconds = int(time.time() - deploy_ts)

    # ------------------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------------------
    db_status = "disconnected"
    db_latency_ms = None
    try:
        t0 = time.perf_counter()
        await asyncio.wait_for(test_connection(), timeout=3)
        db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        db_status = "connected"
    except asyncio.TimeoutError:
        db_status = "timeout"
    except Exception:
        db_status = "error"

    # ------------------------------------------------------------------
    # SMTP
    # ------------------------------------------------------------------
    smtp_status = "not_configured"
    if settings.SMTP_HOST:
        try:
            sock = socket.create_connection(
                (settings.SMTP_HOST, settings.SMTP_PORT),
                timeout=2,
            )
            sock.close()
            smtp_status = "connected"
        except Exception:
            smtp_status = "error"

    # ------------------------------------------------------------------
    # REDIS
    # ------------------------------------------------------------------
    redis_status = "disabled"
    redis_latency_ms = None

    if settings.REDIS_URL:
        client = None
        try:
            client = _redis_client()
            t0 = time.perf_counter()
            await asyncio.wait_for(client.ping(), timeout=2)
            redis_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            redis_status = "connected"
        except asyncio.TimeoutError:
            redis_status = "timeout"
        except redis.ConnectionError:
            redis_status = "offline"
        except Exception:
            redis_status = "error"
        finally:
            await _safe_close_redis(client)

    return {
        "status": "online",
        "uptime_seconds": uptime_seconds,
        "environment": "serverless" if os.environ.get("VERCEL") else "development",
        "database": {"status": db_status, "latency_ms": db_latency_ms},
        "redis": {"status": redis_status, "latency_ms": redis_latency_ms},
        "smtp": {"status": smtp_status},
    }


# ---------------------------------------------------------------------------
# 3. ADMIN DASHBOARD STATS
# ---------------------------------------------------------------------------

@router.get("/dashboard-stats")
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
):
    # Application counts by status
    status_res = await session.execute(
        select(Application.status, func.count(Application.id)).group_by(Application.status)
    )
    status_counts = {row[0]: row[1] for row in status_res.all()}

    # Top 5 departments with the most pending stages (bottlenecks)
    bottleneck_res = await session.execute(
        select(Department.name, func.count(ApplicationStage.id))
        .join(ApplicationStage, ApplicationStage.department_id == Department.id)
        .where(ApplicationStage.status == "pending")
        .group_by(Department.name)
        .order_by(func.count(ApplicationStage.id).desc())
        .limit(5)
    )
    bottlenecks = [
        {"department": row[0], "pending_count": row[1]}
        for row in bottleneck_res.all()
    ]

    # 5 most recent audit log entries
    logs_res = await session.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(5)
    )
    recent_logs = [log.model_dump() for log in logs_res.scalars().all()]

    return {
        "metrics": {
            "total_applications": sum(status_counts.values()),
            "pending": status_counts.get("pending", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
            "rejected": status_counts.get("rejected", 0),
        },
        "top_bottlenecks": bottlenecks,
        "recent_activity": recent_logs,
    }


# ---------------------------------------------------------------------------
# 4. REDIS STATS
# ---------------------------------------------------------------------------

@router.get("/redis-stats")
async def get_redis_statistics(_: User = Depends(require_admin)):
    if not settings.REDIS_URL:
        return {"status": "disabled", "message": "Redis is not configured."}

    if _redis_metrics_in_cooldown():
        return _redis_metrics_cooldown_response("timeout")

    client = None
    try:
        client = _redis_client()

        info, dbsize = await asyncio.gather(
            asyncio.wait_for(client.info(), timeout=3),
            asyncio.wait_for(client.dbsize(), timeout=3),
        )

        # Sample up to 5 active rate-limit keys (informational only)
        sampled_keys: list[str] = []
        async for key in client.scan_iter(match="LIMITER/*", count=100):
            sampled_keys.append(key)
            if len(sampled_keys) >= 5:
                break

        # Count active rate-limit keys without fetching all of them
        active_limit_count = 0
        async for _ in client.scan_iter(match="LIMITER/*", count=200):
            active_limit_count += 1
            if active_limit_count >= 500:  # hard cap on counting loop
                break

        return {
            "status": "online",
            "metrics": {
                "redis_version": info.get("redis_version"),
                "uptime_days": info.get("uptime_in_days"),
                "clients": {
                    "connected": info.get("connected_clients"),
                    "blocked": info.get("blocked_clients"),
                },
                "memory": {
                    "used": info.get("used_memory_human"),
                    "peak": info.get("used_memory_peak_human"),
                    "fragmentation": info.get("mem_fragmentation_ratio"),
                },
                "db": {
                    "total_keys": dbsize,
                    "active_rate_limit_windows": active_limit_count,
                    "sampled_keys": sampled_keys,
                },
            },
        }

    except (asyncio.TimeoutError, RedisTimeoutError):
        _mark_redis_metrics_cooldown("timeout")
        return {"status": "timeout", "message": "Redis did not respond in time."}
    except RedisConnectionError:
        _mark_redis_metrics_cooldown("connection_error")
        return {"status": "offline", "message": "Redis server unreachable."}
    except Exception as e:
        logger.error(f"Redis stats error: {e}")
        return {"status": "error", "message": "Failed to retrieve Redis stats."}
    finally:
        await _safe_close_redis(client)


# ---------------------------------------------------------------------------
# 5. TRAFFIC STATS
# ---------------------------------------------------------------------------

MAX_TRAFFIC_KEYS = 200  # hard cap – prevents unbounded scan on large datasets


@router.get("/traffic-stats")
async def get_traffic_statistics(_: User = Depends(require_admin)):
    if not settings.REDIS_URL:
        return {"status": "disabled", "data": []}

    if _redis_metrics_in_cooldown():
        return {
            "total_endpoints_tracked": 0,
            "data": [],
            **_redis_metrics_cooldown_response("timeout"),
        }

    client = None
    try:
        client = _redis_client()

        # Collect keys up to hard cap
        keys: list[str] = []
        async for key in client.scan_iter(match="TRAFFIC:*", count=500):
            keys.append(key)
            if len(keys) >= MAX_TRAFFIC_KEYS:
                break

        if not keys:
            return {"status": "online", "total_endpoints_tracked": 0, "data": []}

        # Batch-fetch all values in a single round-trip
        values = await client.mget(*keys)

        traffic_data = []
        for key, count in zip(keys, values):
            parts = key.split(":", 2)
            if len(parts) == 3:
                traffic_data.append({
                    "method": parts[1],
                    "path": parts[2],
                    "hits": int(count) if count else 0,
                })

        traffic_data.sort(key=lambda x: x["hits"], reverse=True)

        return {
            "status": "online",
            "total_endpoints_tracked": len(traffic_data),
            "capped": len(keys) == MAX_TRAFFIC_KEYS,
            "data": traffic_data,
        }

    except (asyncio.TimeoutError, RedisTimeoutError):
        _mark_redis_metrics_cooldown("timeout")
        return {
            "status": "timeout",
            "message": "Redis did not respond in time.",
            "total_endpoints_tracked": 0,
            "data": [],
        }
    except RedisConnectionError:
        _mark_redis_metrics_cooldown("connection_error")
        return {
            "status": "offline",
            "message": "Redis server unreachable.",
            "total_endpoints_tracked": 0,
            "data": [],
        }
    except Exception as e:
        logger.error(f"Traffic stats error: {e}")
        return {"status": "error", "message": "Failed to retrieve traffic stats."}
    finally:
        await _safe_close_redis(client)


# ---------------------------------------------------------------------------
# 6. CLEAR CACHE  –  scoped, audited, no flushdb
# ---------------------------------------------------------------------------

CACHE_SCOPES = {
    "rate_limits": "LIMITER/*",
    "traffic": "TRAFFIC:*",
}


@router.post("/clear-cache")
async def clear_system_cache(
    scope: str = Query(
        default="rate_limits",
        description="Which cache namespace to clear. Allowed: 'rate_limits', 'traffic'.",
    ),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    """
    Clears Redis keys within the requested namespace.

    - scope='rate_limits' - clears active throttle windows (LIMITER/*)
    - scope='traffic'     - clears traffic hit counters (TRAFFIC:*)

    The 'all' / flushdb option has been intentionally removed to prevent
    wiping shared Redis state (sessions, OTPs, etc.).
    """
    if scope not in CACHE_SCOPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope '{scope}'. Allowed values: {list(CACHE_SCOPES.keys())}",
        )

    if not settings.REDIS_URL:
        raise HTTPException(status_code=400, detail="Redis is not configured.")

    client = None
    try:
        client = _redis_client()
        pattern = CACHE_SCOPES[scope]

        deleted = 0
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)
            deleted += 1

        # Audit trail – who cleared what and when
        await _write_audit(
            session,
            current_user,
            action="cache_clear",
            detail=f"scope={scope} keys_deleted={deleted}",
        )

        logger.info(
            f"Cache cleared by user {current_user.id} | scope={scope} | deleted={deleted}"
        )
        return {"status": "success", "scope": scope, "keys_deleted": deleted}

    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache.")
    finally:
        await _safe_close_redis(client)