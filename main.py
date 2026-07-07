"""Personal AI Chief of Staff — entry point.

Starts everything: memory, tools, sub-agents, morning routine scheduler,
voice (if enabled), and the chat interface. Every subsystem loads with
graceful degradation — if one integration fails, the rest keep working.
"""

import importlib
import threading

from config.settings import settings
from core.agent import ChiefOfStaff, tools
from core.brain import brain
from core.logger import get_logger
from ui import chat_interface, first_run

log = get_logger("main")

# Modules that register tools into the global registry when imported.
TOOL_MODULES = [
    "integrations.gmail_agent",
    "integrations.calendar_agent",
    "integrations.github_agent",
    "integrations.linkedin_agent",
    "integrations.facebook_agent",
    "core.computer_use",
    "agents.marketer",
    "agents.job_hunter",
    "agents.assistant",
    "agents.seller",
    "agents.dev_monitor",
]


def load_tool_modules() -> None:
    for mod in TOOL_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:
            log.warning("Module %s disabled: %s", mod, e)
            chat_interface.info(f"({mod.split('.')[-1]} disabled: {e})")


def start_morning_routine(agent) -> None:
    if not settings.enable_morning_routine:
        return
    try:
        from core.scheduler import start_scheduler

        start_scheduler(agent)
        chat_interface.info(f"Morning routine scheduled for {settings.morning_routine_time}.")
    except Exception as e:
        log.warning("Scheduler disabled: %s", e)


def build_speak_fn():
    if not settings.enable_voice:
        return None
    try:
        from core.voice import speak

        return speak
    except Exception as e:
        log.warning("Voice output disabled: %s", e)
        return None


def start_wake_word(agent, speak_fn) -> None:
    if not (settings.enable_voice and settings.enable_wake_word):
        return
    try:
        from core.wake_word import WakeWordListener

        listener = WakeWordListener(agent, speak_fn)
        thread = threading.Thread(target=listener.run_forever, daemon=True)
        thread.start()
        chat_interface.info(f'Listening for "{settings.wake_word}" in the background.')
    except Exception as e:
        log.warning("Wake word disabled: %s", e)
        chat_interface.info(f"(voice wake word disabled: {e})")


def main() -> None:
    if not brain.available:
        chat_interface.error(
            "No AI brain configured. Copy .env.example to .env and set "
            "ANTHROPIC_API_KEY (and optionally GEMINI_API_KEY), then restart."
        )
        return

    if first_run.needs_first_run():
        first_run.run_wizard()

    load_tool_modules()
    chat_interface.info(f"{len(tools)} tools loaded.")

    agent = ChiefOfStaff(confirm_callback=chat_interface.confirm)
    speak_fn = build_speak_fn()
    start_wake_word(agent, speak_fn)
    start_morning_routine(agent)

    chat_interface.chat_loop(agent, speak_fn=speak_fn)


if __name__ == "__main__":
    main()
