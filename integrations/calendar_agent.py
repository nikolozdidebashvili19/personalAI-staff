"""Google Calendar integration — read schedule, create events."""

from datetime import datetime, timedelta, timezone

from core.agent import tools
from core.logger import get_logger
from core.memory import memory
from integrations.google_auth import calendar_service

log = get_logger("calendar")


def _fmt_event(ev: dict) -> str:
    start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", "?"))
    end = ev.get("end", {}).get("dateTime", ev.get("end", {}).get("date", ""))
    attendees = ", ".join(a.get("email", "") for a in ev.get("attendees", [])[:5])
    line = f"[{ev.get('id', '')[:12]}] {start} → {end} | {ev.get('summary', '(no title)')}"
    if ev.get("location"):
        line += f" @ {ev['location']}"
    if attendees:
        line += f" (with {attendees})"
    return line


@tools.register(
    "list_calendar_events",
    "List upcoming Google Calendar events. Use days=1 for today's schedule.",
    {
        "type": "object",
        "properties": {"days": {"type": "integer", "default": 1, "description": "How many days ahead"}},
    },
)
def list_calendar_events(days: int = 1) -> str:
    svc = calendar_service()
    now = datetime.now(timezone.utc)
    resp = svc.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=(now + timedelta(days=days)).isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=25,
    ).execute()
    events = resp.get("items", [])
    if not events:
        return f"No events in the next {days} day(s). The calendar is clear."
    return "\n".join(_fmt_event(e) for e in events)


@tools.register(
    "create_calendar_event",
    "Create a Google Calendar event / book a meeting. Times are ISO 8601 in the user's "
    "timezone, e.g. '2026-07-09T14:00:00'. User confirms before it is created.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "ISO datetime"},
            "end": {"type": "string", "description": "ISO datetime (default: start + 30 min)"},
            "attendees": {"type": "array", "items": {"type": "string"}, "description": "attendee emails"},
            "description": {"type": "string"},
            "location": {"type": "string"},
        },
        "required": ["title", "start"],
    },
    requires_confirmation=True,
)
def create_calendar_event(
    title: str,
    start: str,
    end: str = "",
    attendees: list | None = None,
    description: str = "",
    location: str = "",
) -> str:
    svc = calendar_service()
    tz = memory.profile.get("schedule", {}).get("timezone", "UTC")
    if not end:
        end = (datetime.fromisoformat(start) + timedelta(minutes=30)).isoformat()
    body = {
        "summary": title,
        "start": {"dateTime": start, "timeZone": tz},
        "end": {"dateTime": end, "timeZone": tz},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    ev = svc.events().insert(calendarId="primary", body=body, sendUpdates="all").execute()
    return f"Event created: {title} at {start} — {ev.get('htmlLink', '')}"


@tools.register(
    "delete_calendar_event",
    "Delete a calendar event by its id (from list_calendar_events). User confirms first.",
    {
        "type": "object",
        "properties": {"event_id": {"type": "string"}},
        "required": ["event_id"],
    },
    requires_confirmation=True,
)
def delete_calendar_event(event_id: str) -> str:
    svc = calendar_service()
    svc.events().delete(calendarId="primary", eventId=event_id, sendUpdates="all").execute()
    return f"Event {event_id} deleted."
