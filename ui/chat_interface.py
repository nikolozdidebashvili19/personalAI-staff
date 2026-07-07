"""Text chat interface — the always-available fallback when voice is off."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from config.settings import settings

console = Console()


def banner() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]{settings.agent_name}[/bold cyan] — your Personal AI Chief of Staff\n"
            f"Type to chat.  [dim]'exit' quits · 'voice on/off' toggles voice[/dim]",
            border_style="cyan",
        )
    )


def show_reply(text: str) -> None:
    console.print()
    console.print(f"[bold cyan]{settings.agent_name}:[/bold cyan]")
    console.print(Markdown(text))
    console.print()


def ask(prompt: str) -> str:
    return console.input(f"[bold green]{prompt}[/bold green] ")


def confirm(question: str) -> bool:
    return console.input(f"\n[bold yellow]⚠️  {question} (y/n):[/bold yellow] ").strip().lower().startswith("y")


def info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")


def error(msg: str) -> None:
    console.print(f"[bold red]{msg}[/bold red]")


def chat_loop(agent, speak_fn=None) -> None:
    """REPL. speak_fn(text) is called with each reply when voice output is on."""
    banner()
    voice_on = speak_fn is not None
    while True:
        try:
            user_input = console.input("[bold green]You:[/bold green] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            console.print(f"[cyan]{settings.agent_name}: See you later![/cyan]")
            break
        if user_input.lower() == "voice off":
            voice_on = False
            info("Voice output off.")
            continue
        if user_input.lower() == "voice on":
            voice_on = speak_fn is not None
            info("Voice output on." if voice_on else "Voice unavailable (dependencies missing).")
            continue

        with console.status("[cyan]thinking…[/cyan]"):
            try:
                reply = agent.run_turn(user_input)
            except Exception as e:
                error(f"Something went wrong: {e}")
                continue
        show_reply(reply)
        if voice_on and speak_fn is not None:
            try:
                speak_fn(reply)
            except Exception:
                pass  # voice failure must never kill the chat
