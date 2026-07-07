"""Job Hunter sub-agent — search, filter by profile, track applications."""

import json
import sqlite3

from config.settings import settings
from core.agent import tools
from core.brain import brain
from core.memory import memory

_conn = sqlite3.connect(settings.memory_db_path, check_same_thread=False)
_conn.execute(
    """CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT DEFAULT (datetime('now','localtime')),
        company TEXT, role TEXT, url TEXT,
        status TEXT DEFAULT 'applied',
        notes TEXT
    )"""
)
_conn.commit()


@tools.register(
    "find_matching_jobs",
    "Search for jobs matching the user's profile (roles/locations from memory unless "
    "overridden) and rank the results by fit.",
    {
        "type": "object",
        "properties": {
            "keywords": {"type": "string", "description": "Override search keywords (optional)"},
            "location": {"type": "string", "description": "Override location (optional)"},
        },
    },
)
def find_matching_jobs(keywords: str = "", location: str = "") -> str:
    jp = memory.profile.get("job_preferences", {})
    keywords = keywords or ", ".join(jp.get("roles", [])) or memory.profile.get("occupation", "software developer")
    location = location or (jp.get("locations", ["Remote"]) or ["Remote"])[0]

    from integrations.linkedin_agent import linkedin_job_search

    raw = linkedin_job_search(keywords, location)
    if "not logged in" in raw.lower():
        return raw

    profile = memory.profile_summary()
    avoid = ", ".join(jp.get("avoid", [])) or "nothing in particular"
    return brain.quick(
        f"Job search results:\n{raw[:6000]}\n\nUser profile:\n{profile}\nAvoid: {avoid}\n\n"
        "Pick the 5 best-fitting jobs. For each: title, company, location, why it fits (one line). "
        "Then say which ones look like 'Easy Apply' candidates.",
        system="You are a picky career agent who only recommends genuinely good fits.",
    )


@tools.register(
    "track_application",
    "Record a job application in the tracker (call after applying, or when the user says "
    "they applied somewhere).",
    {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "role": {"type": "string"},
            "url": {"type": "string"},
            "status": {"type": "string", "default": "applied",
                       "description": "applied | interviewing | rejected | offer | ghosted"},
            "notes": {"type": "string"},
        },
        "required": ["company", "role"],
    },
)
def track_application(company: str, role: str, url: str = "", status: str = "applied", notes: str = "") -> str:
    _conn.execute(
        "INSERT INTO applications (company, role, url, status, notes) VALUES (?,?,?,?,?)",
        (company, role, url, status, notes),
    )
    _conn.commit()
    memory.remember_event("job_application", f"{role} at {company}", status)
    return f"Tracked: {role} at {company} ({status})"


@tools.register(
    "update_application_status",
    "Update the status of a tracked application (e.g. when a company replies).",
    {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "status": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["company", "status"],
    },
)
def update_application_status(company: str, status: str, notes: str = "") -> str:
    cur = _conn.execute(
        "UPDATE applications SET status=?, notes=COALESCE(NULLIF(?,'') , notes) "
        "WHERE company LIKE ? ORDER BY id DESC",
        (status, notes, f"%{company}%"),
    )
    _conn.commit()
    if cur.rowcount == 0:
        return f"No tracked application found for '{company}'."
    return f"Updated {cur.rowcount} application(s) at {company} to '{status}'."


@tools.register(
    "application_report",
    "Show the status of all tracked job applications.",
    {"type": "object", "properties": {}},
)
def application_report() -> str:
    rows = _conn.execute(
        "SELECT created, company, role, status, notes FROM applications ORDER BY id DESC LIMIT 30"
    ).fetchall()
    if not rows:
        return "No applications tracked yet."
    return "\n".join(
        f"[{r[0][:10]}] {r[2]} at {r[1]} — {r[3]}" + (f" ({r[4]})" if r[4] else "") for r in rows
    )


@tools.register(
    "draft_cover_letter",
    "Write a short, tailored cover letter / application message for a specific job, "
    "based on the user's profile and resume facts.",
    {
        "type": "object",
        "properties": {
            "job_description": {"type": "string", "description": "The job posting text or summary"},
        },
        "required": ["job_description"],
    },
)
def draft_cover_letter(job_description: str) -> str:
    return brain.quick(
        f"Job posting:\n{job_description[:3000]}\n\nCandidate profile:\n{memory.profile_summary()}\n\n"
        "Write a tight 150-word application message: specific, confident, zero clichés, "
        "matching the candidate's real experience. Output only the message.",
        system="You write cover letters recruiters actually finish reading.",
    )
