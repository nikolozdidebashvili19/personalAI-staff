"""First-run wizard — get to know the user before doing anything else."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from config.settings import settings
from core.memory import memory

console = Console()


def needs_first_run() -> bool:
    return not memory.profile.get("name")


def run_wizard() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]Welcome! I'm {settings.agent_name}, your Personal AI Chief of Staff.[/bold cyan]\n"
            "Let me get to know you before we start.",
            border_style="cyan",
        )
    )

    name = console.input("[green]1. What's your name?[/green] ").strip()
    if name:
        memory.update_profile("name", name)

    work = console.input("[green]2. What do you do for work?[/green] ").strip()
    if work:
        memory.update_profile("occupation", work)

    goal = console.input(
        "[green]3. What's your main goal right now?[/green] "
        "[dim](job hunting / growing online / managing clients / all of the above)[/dim] "
    ).strip()
    if goal:
        memory.update_profile("goals", [goal])

    tz = console.input(
        f"[green]4. What timezone are you in?[/green] [dim](enter for {settings.user_timezone})[/dim] "
    ).strip()
    memory.update_profile("schedule.timezone", tz or settings.user_timezone)

    console.input(
        "[green]5. Do you have a resume PDF?[/green] "
        f"[dim]Drop it at {settings.resume_path} and press Enter (or Enter to skip).[/dim] "
    )
    if Path(settings.resume_path).exists():
        memory.add_fact("Resume is available at " + str(settings.resume_path))
        console.print("[dim]✓ Resume found.[/dim]")
    else:
        console.print("[dim]No resume yet — you can add it later.[/dim]")

    memory.save_profile()
    console.print(
        Panel.fit(
            "[bold]Great! I've saved everything I need to know about you.[/bold]\n"
            f"Say '{settings.wake_word}' anytime to wake me up, or just type to chat.\n"
            f"I'll run your morning briefing at {settings.morning_routine_time}.\n\n"
            "What would you like me to do first?",
            border_style="green",
        )
    )
