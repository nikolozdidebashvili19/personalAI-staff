"""LinkedIn via browser automation (no official API for personal accounts).

Uses the persistent browser profile from core.computer_use — the user logs in
once in the visible browser window and stays logged in. Direct selectors are
tried first; the vision loop is the fallback so we never get stuck.
"""

import time
import urllib.parse

from core.agent import tools
from core.computer_use import browser, vision_browser_task
from core.logger import get_logger
from core.memory import memory

log = get_logger("linkedin")


def _ensure_login() -> str | None:
    """Returns an error message if the user must log in first, else None."""
    b = browser()
    b.open("https://www.linkedin.com/feed/")
    text = b.text(1500).lower()
    if "sign in" in text and "start a post" not in text:
        return (
            "LinkedIn is not logged in. The browser window is open — ask the user to "
            "log in there once (the session will be remembered), then try again."
        )
    return None


@tools.register(
    "linkedin_post",
    "Publish a post on the user's LinkedIn feed. Write the content in the user's "
    "posting style (see profile). The user confirms before it is published.",
    {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "Full post text"}},
        "required": ["content"],
    },
    requires_confirmation=True,
)
def linkedin_post(content: str) -> str:
    err = _ensure_login()
    if err:
        return err
    b = browser()
    try:
        # fast path: known UI selectors
        b.click_selector("button.share-box-feed-entry__trigger")
        time.sleep(2)
        b.page.keyboard.type(content, delay=15)
        time.sleep(1)
        b.click_selector("button.share-actions__primary-action")
        time.sleep(3)
        memory.remember_event("linkedin_post", content[:200], "posted")
        return "Posted to LinkedIn."
    except Exception as e:
        log.info("Selector path failed (%s) — falling back to vision", e)
        result = vision_browser_task(
            f"Publish a LinkedIn post from the feed page. Click the 'Start a post' box, "
            f"type exactly this text, then click the Post button:\n\n{content}"
        )
        if result.lower().startswith("done"):
            memory.remember_event("linkedin_post", content[:200], "posted (vision)")
        return result


@tools.register(
    "linkedin_job_search",
    "Search LinkedIn Jobs and return the visible listings (title, company, location).",
    {
        "type": "object",
        "properties": {
            "keywords": {"type": "string"},
            "location": {"type": "string", "default": ""},
        },
        "required": ["keywords"],
    },
)
def linkedin_job_search(keywords: str, location: str = "") -> str:
    err = _ensure_login()
    if err:
        return err
    b = browser()
    url = "https://www.linkedin.com/jobs/search/?keywords=" + urllib.parse.quote(keywords)
    if location:
        url += "&location=" + urllib.parse.quote(location)
    b.open(url)
    time.sleep(3)
    b.scroll(1200)
    listings = b.text(5000)
    memory.remember_event("job_search", f"LinkedIn: {keywords} {location}", "listed")
    return f"LinkedIn job results for '{keywords}' {location}:\n{listings}"


@tools.register(
    "linkedin_apply",
    "Apply to a LinkedIn job (Easy Apply) using the user's saved LinkedIn profile/resume. "
    "Give the exact job title + company as seen in search results, or a job URL. "
    "The user confirms before applying.",
    {
        "type": "object",
        "properties": {
            "job": {"type": "string", "description": "Job URL, or 'title at company' from search results"},
        },
        "required": ["job"],
    },
    requires_confirmation=True,
)
def linkedin_apply(job: str) -> str:
    err = _ensure_login()
    if err:
        return err
    if job.startswith("http"):
        browser().open(job)
    result = vision_browser_task(
        f"Apply to this LinkedIn job: {job}. If not already on the job page, find and open it. "
        "Click 'Easy Apply', fill any required fields with the user's saved info, and submit. "
        "If the application requires uploading documents that aren't pre-saved or answering "
        "questions you can't answer confidently, use wait_for_user instead of guessing."
    )
    status = "applied" if result.lower().startswith("done") else "attempted"
    memory.remember_event("job_application", job[:200], status)
    return result
