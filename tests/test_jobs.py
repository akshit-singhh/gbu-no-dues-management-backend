import pytest


pytestmark = pytest.mark.asyncio


async def test_trigger_stale_notifications_rejects_invalid_secret(client):
    res = await client.post("/api/jobs/trigger-stale-notifications?secret_key=wrong")
    assert res.status_code == 403
    assert "Invalid or missing Job Secret Key." in res.text


async def test_trigger_stale_notifications_skips_when_no_stale(client, monkeypatch):
    monkeypatch.setenv("JOB_SECRET", "unit-test-secret")

    res = await client.post(
        "/api/jobs/trigger-stale-notifications?secret_key=unit-test-secret"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "skipped"
