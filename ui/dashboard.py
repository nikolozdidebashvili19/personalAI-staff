"""Optional status dashboard — run `python -m ui.dashboard` for a live overview."""

import time

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel

from config.settings import settings
from core.memory import memory


def _build() -> Layout:
    layout = Layout()
    layout.split_column(Layout(name="top", size=7), Layout(name="bottom"))
    layout["top"].split_row(Layout(name="profile"), Layout(name="status"))

    layout["profile"].update(
        Panel(memory.profile_summary()[:500] or "(empty)", title="👤 Profile", border_style="cyan")
    )
    status = (
        f"Agent: {settings.agent_name}\n"
        f"Model: {settings.claude_model}\n"
        f"Voice: {'on' if settings.enable_voice else 'off'} | "
        f"Wake word: '{settings.wake_word}'\n"
        f"Morning routine: {settings.morning_routine_time}"
    )
    layout["status"].update(Panel(status, title="⚙️ Status", border_style="green"))

    events = memory.events_since(hours=24)
    lines = "\n".join(
        f"[{e['timestamp'][11:16]}] {e['type']}: {e['description'][:80]}" for e in events[-18:]
    ) or "(no activity in the last 24h)"
    layout["bottom"].update(Panel(lines, title="📜 Last 24 hours", border_style="magenta"))
    return layout


def main() -> None:
    console = Console()
    with Live(_build(), console=console, refresh_per_second=0.5) as live:
        try:
            while True:
                time.sleep(5)
                live.update(_build())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
