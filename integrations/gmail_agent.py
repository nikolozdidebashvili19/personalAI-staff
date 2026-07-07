"""Gmail integration — read, summarize, draft, reply, send.

Sending always requires user confirmation (enforced by the agent loop).
"""

import base64
from email.message import EmailMessage

from core.agent import tools
from core.logger import get_logger
from integrations.google_auth import gmail_service

log = get_logger("gmail")


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _body_text(payload: dict) -> str:
    """Extract plain text from a message payload (walks multipart)."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _body_text(part)
        if text:
            return text
    return ""


@tools.register(
    "check_emails",
    "List recent emails from the Gmail inbox. Optional Gmail search query "
    "(e.g. 'is:unread', 'from:boss@x.com newer_than:2d').",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail search query", "default": "in:inbox"},
            "max_results": {"type": "integer", "default": 10},
        },
    },
)
def check_emails(query: str = "in:inbox", max_results: int = 10) -> str:
    svc = gmail_service()
    resp = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    ids = [m["id"] for m in resp.get("messages", [])]
    if not ids:
        return "No emails match."
    lines = []
    for mid in ids:
        msg = svc.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        unread = "UNREAD" in msg.get("labelIds", [])
        lines.append(
            f"[{mid}]{' 🔵' if unread else ''} From: {_header(msg, 'From')} | "
            f"Subject: {_header(msg, 'Subject')} | {_header(msg, 'Date')} | "
            f"Snippet: {msg.get('snippet', '')[:120]}"
        )
    return "\n".join(lines)


@tools.register(
    "read_email",
    "Read the full body of one email by its id (from check_emails).",
    {
        "type": "object",
        "properties": {"email_id": {"type": "string"}},
        "required": ["email_id"],
    },
)
def read_email(email_id: str) -> str:
    svc = gmail_service()
    msg = svc.users().messages().get(userId="me", id=email_id, format="full").execute()
    body = _body_text(msg.get("payload", {})) or msg.get("snippet", "")
    return (
        f"From: {_header(msg, 'From')}\nTo: {_header(msg, 'To')}\n"
        f"Subject: {_header(msg, 'Subject')}\nDate: {_header(msg, 'Date')}\n\n{body[:4000]}"
    )


def _build_message(to: str, subject: str, body: str, thread_headers: dict | None = None) -> dict:
    mime = EmailMessage()
    mime["To"] = to
    mime["Subject"] = subject
    if thread_headers:
        for k, v in thread_headers.items():
            mime[k] = v
    mime.set_content(body)
    return {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}


@tools.register(
    "draft_email",
    "Create a Gmail draft (does NOT send). Use to prepare a message for the user's review.",
    {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
def draft_email(to: str, subject: str, body: str) -> str:
    svc = gmail_service()
    draft = svc.users().drafts().create(
        userId="me", body={"message": _build_message(to, subject, body)}
    ).execute()
    return f"Draft created (id {draft['id']}). It is in the user's Gmail drafts folder."


@tools.register(
    "send_email",
    "Send an email from the user's Gmail account. The user will be asked to confirm first.",
    {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    requires_confirmation=True,
)
def send_email(to: str, subject: str, body: str) -> str:
    svc = gmail_service()
    sent = svc.users().messages().send(userId="me", body=_build_message(to, subject, body)).execute()
    return f"Email sent to {to} (id {sent['id']})."


@tools.register(
    "reply_email",
    "Reply to an existing email (stays in the same thread). User confirms before sending.",
    {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "id of the email being replied to"},
            "body": {"type": "string"},
        },
        "required": ["email_id", "body"],
    },
    requires_confirmation=True,
)
def reply_email(email_id: str, body: str) -> str:
    svc = gmail_service()
    original = svc.users().messages().get(
        userId="me", id=email_id, format="metadata",
        metadataHeaders=["From", "Subject", "Message-ID"],
    ).execute()
    to = _header(original, "From")
    subject = _header(original, "Subject")
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    message = _build_message(
        to, subject, body,
        thread_headers={
            "In-Reply-To": _header(original, "Message-ID"),
            "References": _header(original, "Message-ID"),
        },
    )
    message["threadId"] = original.get("threadId")
    sent = svc.users().messages().send(userId="me", body=message).execute()
    return f"Reply sent to {to} (id {sent['id']})."
