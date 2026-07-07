"""Morning routine scheduler.

Runs read-only gathering tasks (email summary, calendar, GitHub, job tracker),
composes a spoken-style briefing, prints it, pops a notification, and speaks it.
Anything irreversible (posting, applying) is only *suggested* in the briefing —
the agent never takes those actions without the user in the loop.
"""

import threading
import time

import schedule

from config.settings import settings
from core.brain import brain
from core.logger import get_logger
from core.memory import memory

log = get_logger("scheduler")

# Task registry: name -> zero-arg callable returning a text section.
# Configurable: remove/add entries in code or disable via profile preferences.
def _routine_tasks() -> dict:
    tasks = {}
    try:
        from agents.assistant import summarize_inbox

        tasks["emails"] = lambda: summarize_inbox(hours=16)
    except Exception:
        pass
    try:
        from integrations.calendar_agent import list_calendar_events

        tasks["calendar"] = lambda: list_calendar_events(days=1)
    except Exception:
        pass
    try:
        from agents.dev_monitor import dev_report

        tasks["github"] = dev_report
    except Exception:
        pass
    try:
        from agents.job_hunter import application_report

        tasks["job applications"] = application_report
    except Exception:
        pass
    return tasks


def run_morning_routine(agent=None) -> str:
    log.info("Running morning routine")
    sections = []
    for name, fn in _routine_tasks().items():
        try:
            sections.append(f"### {name}\n{fn()}")
        except Exception as e:
            sections.append(f"### {name}\n(unavailable: {e})")

    user = memory.profile.get("name") or "there"
    briefing = brain.quick(
        f"Raw morning data:\n" + "\n\n".join(sections)[:8000] + "\n\n"
        f"Compose a morning briefing for {user}, spoken by their assistant {settings.agent_name}. "
        "Start with 'Good morning'. Cover: urgent emails, today's meetings, GitHub items needing "
        "action, job application status. End by suggesting ONE useful thing to do first "
        "(e.g. a LinkedIn post idea or a job worth applying to). Friendly, under 200 words.",
        system="You are a warm, efficient chief of staff giving a daily briefing.",
    )

    memory.remember_event("morning_routine", "Daily briefing delivered", "success")

    print(f"\n{'='*60}\n🌅 MORNING BRIEFING\n{'='*60}\n{briefing}\n{'='*60}\n")
    try:
        from ui.notifications import notify

        notify(f"{settings.agent_name} — Morning Briefing", briefing[:200])
    except Exception:
        pass
    if settings.enable_voice:
        try:
            from core.voice import speak

            speak(briefing)
        except Exception:
            pass
    return briefing


def start_scheduler(agent=None) -> None:
    routine_time = memory.profile.get("schedule", {}).get(
        "morning_routine_time", settings.morning_routine_time
    )
    schedule.every().day.at(routine_time).do(run_morning_routine, agent)

    def loop():
        while True:
            schedule.run_pending()
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="scheduler").start()
    log.info("Scheduler started — morning routine at %s", routine_time)


# Let the user trigger it on demand too ("give me my briefing")
from core.agent import tools  # noqa: E402


@tools.register(
    "morning_briefing",
    "Run the full morning briefing right now (emails + calendar + GitHub + job tracker).",
    {"type": "object", "properties": {}},
)
def morning_briefing() -> str:
    return run_morning_routine()
