"""Assistant sub-agent — email triage and drafting in the user's voice."""

from core.agent import tools
from core.brain import brain
from core.memory import memory


@tools.register(
    "summarize_inbox",
    "Read recent unread emails and produce a prioritized summary: urgent first, "
    "then needs-reply, then FYI. Use for 'check my emails'.",
    {
        "type": "object",
        "properties": {"hours": {"type": "integer", "default": 24}},
    },
)
def summarize_inbox(hours: int = 24) -> str:
    from integrations.gmail_agent import check_emails

    days = max(1, round(hours / 24))
    raw = check_emails(query=f"is:unread newer_than:{days}d", max_results=15)
    if raw.startswith("No emails"):
        return "Inbox zero — no unread emails. 🎉"
    return brain.quick(
        f"Unread emails:\n{raw}\n\n"
        "Summarize as a briefing: 1) 🔴 urgent (why), 2) ✉️ needs a reply (suggest what to say "
        "in one line each), 3) 📋 FYI / can ignore. Reference senders by name. Be brief.",
        system="You are a razor-sharp executive assistant.",
    )


@tools.register(
    "draft_reply_in_style",
    "Draft a reply to a specific email in the user's writing style. Returns the draft — "
    "show it to the user, then send with reply_email once approved.",
    {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "id from check_emails"},
            "intent": {"type": "string", "description": "What the reply should say/achieve"},
        },
        "required": ["email_id", "intent"],
    },
)
def draft_reply_in_style(email_id: str, intent: str) -> str:
    from integrations.gmail_agent import read_email

    original = read_email(email_id)
    style = memory.profile.get("writing_style") or "friendly, concise, professional but human"
    return brain.quick(
        f"Original email:\n{original[:3000]}\n\nThe user wants to reply with this intent: {intent}\n"
        f"User's writing style: {style}\n\n"
        "Write the reply body only (no subject line). Match the user's voice.",
        system="You draft emails indistinguishable from ones the user writes themselves.",
    )
