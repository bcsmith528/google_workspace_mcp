"""Tests for list_gmail_drafts and update_gmail_draft tools."""

import base64
from email import policy
from email.parser import BytesParser
import os
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.utils import UserInputError  # noqa: E402
from gmail.gmail_tools import (  # noqa: E402
    list_gmail_drafts,
    update_gmail_draft,
)


def _unwrap(tool):
    """Unwrap FunctionTool + decorators to the original async function."""
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _draft_metadata(draft_id, subject, to, from_addr="user@example.com", snippet=""):
    return {
        "id": draft_id,
        "message": {
            "id": f"msg_{draft_id}",
            "threadId": f"thread_{draft_id}",
            "snippet": snippet,
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": from_addr},
                    {"name": "To", "value": to},
                ]
            },
        },
    }


def _existing_draft(headers, parts=None):
    payload = {"headers": [{"name": k, "value": v} for k, v in headers.items()]}
    if parts:
        payload["mimeType"] = "multipart/mixed"
        payload["parts"] = parts
    return {"id": "r1", "message": {"id": "m_old", "payload": payload}}


def _sent_update(mock_service):
    call = mock_service.users().drafts().update.call_args
    raw = call.kwargs["body"]["message"]["raw"]
    parsed = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(raw)
    )
    return call, parsed


def _service_with(existing):
    mock_service = Mock()
    mock_service.users().drafts().get().execute.return_value = existing
    mock_service.users().drafts().update().execute.return_value = {
        "id": "r1",
        "message": {"id": "m_new"},
    }
    return mock_service


@pytest.mark.asyncio
async def test_list_gmail_drafts_returns_formatted_drafts():
    mock_service = Mock()
    mock_service.users().drafts().list().execute.return_value = {
        "drafts": [
            {"id": "r123", "message": {"id": "msg_r123", "threadId": "t1"}},
            {"id": "r456", "message": {"id": "msg_r456", "threadId": "t2"}},
        ]
    }
    mock_service.users().drafts().get().execute.side_effect = [
        _draft_metadata("r123", "First draft", "alice@example.com", snippet="Hi Alice"),
        _draft_metadata("r456", "Second draft", "bob@example.com", snippet="Hi Bob"),
    ]

    result = await _unwrap(list_gmail_drafts)(
        service=mock_service,
        user_google_email="user@example.com",
    )

    assert "Found 2 draft(s)" in result
    assert "Draft ID: r123" in result
    assert "First draft" in result
    assert "alice@example.com" in result
    assert "Draft ID: r456" in result
    assert "Second draft" in result


@pytest.mark.asyncio
async def test_list_gmail_drafts_empty_account():
    mock_service = Mock()
    mock_service.users().drafts().list().execute.return_value = {}

    result = await _unwrap(list_gmail_drafts)(
        service=mock_service,
        user_google_email="user@example.com",
    )

    assert result == "No drafts found."


@pytest.mark.asyncio
async def test_update_carries_forward_omitted_fields_and_replaces_body():
    mock_service = _service_with(
        _existing_draft(
            {
                "Subject": "Re: Case Status",
                "From": "Brad Smith <user@example.com>",
                "To": "rena@example.org",
                "Cc": "cc@example.org",
                "In-Reply-To": "<orig@example.org>",
                "References": "<root@example.org> <orig@example.org>",
            }
        )
    )

    result = await _unwrap(update_gmail_draft)(
        service=mock_service,
        user_google_email="user@example.com",
        draft_id="r1",
        body="New body text",
        include_signature=False,
    )

    call, parsed = _sent_update(mock_service)
    assert call.kwargs["id"] == "r1"
    assert call.kwargs["userId"] == "me"
    assert "threadId" not in call.kwargs["body"]["message"]
    assert parsed["To"] == "rena@example.org"
    assert parsed["Cc"] == "cc@example.org"
    assert parsed["Subject"] == "Re: Case Status"
    assert parsed["In-Reply-To"] == "<orig@example.org>"
    assert "<root@example.org>" in parsed["References"]
    assert "Brad Smith" in parsed["From"] and "user@example.com" in parsed["From"]
    assert "New body text" in parsed.get_body(preferencelist=("plain",)).get_content()
    assert "Draft ID: r1" in result and "Message ID: m_new" in result
    assert "Kept from the existing draft" in result


@pytest.mark.asyncio
async def test_update_replaces_and_clears_fields_when_given():
    mock_service = _service_with(
        _existing_draft(
            {
                "Subject": "Old subject",
                "From": "user@example.com",
                "To": "old@example.org",
                "Cc": "drop@example.org",
            }
        )
    )

    await _unwrap(update_gmail_draft)(
        service=mock_service,
        user_google_email="user@example.com",
        draft_id="r1",
        body="Body",
        subject="New subject",
        to="new@example.org",
        cc="",
        include_signature=False,
    )

    _, parsed = _sent_update(mock_service)
    assert parsed["Subject"] == "New subject"
    assert parsed["To"] == "new@example.org"
    assert parsed["Cc"] is None


@pytest.mark.asyncio
async def test_update_refuses_to_silently_drop_attachments():
    mock_service = _service_with(
        _existing_draft(
            {"Subject": "S", "From": "user@example.com", "To": "a@example.org"},
            parts=[
                {"mimeType": "text/plain", "filename": "", "body": {"data": ""}},
                {
                    "mimeType": "application/pdf",
                    "filename": "receipt.pdf",
                    "body": {"attachmentId": "att1"},
                },
            ],
        )
    )
    mock_service.users().drafts().update.reset_mock()

    with pytest.raises(UserInputError, match="1 attachment"):
        await _unwrap(update_gmail_draft)(
            service=mock_service,
            user_google_email="user@example.com",
            draft_id="r1",
            body="Body",
            include_signature=False,
        )

    mock_service.users().drafts().update.assert_not_called()


@pytest.mark.asyncio
async def test_update_drops_attachments_when_confirmed():
    mock_service = _service_with(
        _existing_draft(
            {"Subject": "S", "From": "user@example.com", "To": "a@example.org"},
            parts=[
                {
                    "mimeType": "application/pdf",
                    "filename": "receipt.pdf",
                    "body": {"attachmentId": "att1"},
                },
            ],
        )
    )

    result = await _unwrap(update_gmail_draft)(
        service=mock_service,
        user_google_email="user@example.com",
        draft_id="r1",
        body="Body",
        drop_existing_attachments=True,
        include_signature=False,
    )

    assert "Draft updated" in result
