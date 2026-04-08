import pytest
from unittest.mock import AsyncMock, patch

from app.services.email_service import (
    send_application_approved_email,
    send_application_created_email,
    send_application_rejected_email,
    send_welcome_email,
)


pytestmark = pytest.mark.asyncio


@patch("app.services.email_service.send_email_async", new_callable=AsyncMock)
async def test_send_welcome_email(mock_send_async):
    data = {
        "full_name": "New Student",
        "enrollment_number": "EN123",
        "roll_number": "R123",
        "email": "student@test.com",
    }

    await send_welcome_email(data)

    mock_send_async.assert_awaited_once()
    args = mock_send_async.await_args.args
    assert args[0] == "student@test.com"
    assert "Welcome" in args[1]


@patch("app.services.email_service.send_email_async", new_callable=AsyncMock)
async def test_send_application_created_email(mock_send_async):
    data = {
        "name": "Submitter One",
        "email": "submit@test.com",
        "application_id": "uuid-123-456",
        "display_id": "NDTEST01",
    }

    await send_application_created_email(data)

    mock_send_async.assert_awaited_once()
    args = mock_send_async.await_args.args
    assert args[0] == "submit@test.com"
    assert "Application Submitted" in args[1]


@patch("app.services.email_service.send_email_async", new_callable=AsyncMock)
async def test_send_approval_email(mock_send_async):
    data = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "roll_number": "R999",
        "enrollment_number": "E999",
        "application_id": "some-uuid",
        "display_id": "NDXYZ01",
    }

    await send_application_approved_email(data)

    mock_send_async.assert_awaited_once()
    args = mock_send_async.await_args.args
    assert args[0] == "jane@example.com"
    assert "Approved" in args[1]


@patch("app.services.email_service.send_email_async", new_callable=AsyncMock)
async def test_send_rejection_email(mock_send_async):
    data = {
        "name": "John Smith",
        "email": "john@example.com",
        "department_name": "Library",
        "remarks": "Book not returned",
    }

    await send_application_rejected_email(data)

    mock_send_async.assert_awaited_once()
    args = mock_send_async.await_args.args
    assert args[0] == "john@example.com"
    assert "Action Required" in args[1]
    assert "Library" in args[2]
    assert "Book not returned" in args[2]
