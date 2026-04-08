import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, UserRole


pytestmark = pytest.mark.asyncio


async def _admin_headers(db_session):
    admin = User(
        name="Metrics Admin",
        email="metrics-admin@test.com",
        role=UserRole.Admin,
        password_hash="pw",
    )
    db_session.add(admin)
    await db_session.commit()
    token = create_access_token(subject=str(admin.id), data={"role": "admin"})
    return {"Authorization": f"Bearer {token}"}


async def test_system_health(client):
    res = await client.get("/api/metrics/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "Online"
    assert "database" in body
    assert "redis" in body


async def test_dashboard_stats_as_admin(client, db_session):
    headers = await _admin_headers(db_session)
    res = await client.get("/api/metrics/dashboard-stats", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "metrics" in body
    assert "top_bottlenecks" in body
    assert "recent_activity" in body


async def test_redis_metrics_and_clear_cache_when_redis_disabled(client, db_session, monkeypatch):
    headers = await _admin_headers(db_session)
    monkeypatch.setattr(settings, "REDIS_URL", None, raising=False)

    redis_stats_res = await client.get("/api/metrics/redis-stats", headers=headers)
    assert redis_stats_res.status_code == 200
    assert redis_stats_res.json()["status"] == "Disabled"

    traffic_res = await client.get("/api/metrics/traffic-stats", headers=headers)
    assert traffic_res.status_code == 200
    assert traffic_res.json()["status"] == "Disabled"

    clear_res = await client.post("/api/metrics/clear-cache", headers=headers)
    assert clear_res.status_code == 400
    assert "Redis not configured" in clear_res.text
